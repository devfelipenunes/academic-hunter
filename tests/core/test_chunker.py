"""Tests for the full-text chunker.

Pure arithmetic over a string: no PDF, no model, no I/O.
"""

import time

import pytest

from academic_hunter.core.fulltext import Chunk, chunk_document, detect_sections
from academic_hunter.core.fulltext.chunker import TARGET_WORDS
from academic_hunter.core.ports.fulltext import ExtractedDocument


def build(*sections, preamble="Journal of Examples\nA. Author\n"):
    """A document from ``(heading, body)`` pairs."""
    parts = [preamble]
    for heading, body in sections:
        parts.append(f"{heading}\n{body}\n")
    return "\n".join(parts)


def words(prefix, count):
    return " ".join(f"{prefix}{i}" for i in range(count))


# Distinct word prefixes per section, so a test can tell which section a chunk's
# text came from. They deliberately do not echo the heading names.
DOC = build(
    ("Abstract", "This paper studies ledgers."),
    ("1. Introduction", words("alpha", 300)),
    ("2. Methods", words("beta", 400)),
    ("References", words("gamma", 500)),
)


def chunk(path="doi:10.1/x", text=DOC, **kwargs):
    return chunk_document(ExtractedDocument(text=text, page_count=9), path, **kwargs)


# ── sections ────────────────────────────────────────────────────────────────


def test_detect_sections_finds_the_headings():
    names = [s.name for s in detect_sections(DOC)]

    assert names == ["preamble", "abstract", "introduction", "method", "references"]


def test_a_section_starts_after_its_heading():
    """The heading is a label, not content — it must not become a chunk's opening."""
    headings = {h for h, _ in [("Abstract", 0), ("1. Introduction", 0),
                               ("2. Methods", 0), ("References", 0)]}

    for section in detect_sections(DOC):
        if section.name == "preamble":
            continue
        opening = DOC[section.start:section.end].lstrip()
        assert not any(opening.startswith(h) for h in headings)


@pytest.mark.parametrize("heading", ["Abstract", "ABSTRACT", "1. Introduction", "2.1 Methods",
                                     "III. Results", "5 Conclusion", "References"])
def test_heading_forms_are_recognised(heading):
    text = f"{heading}\n" + words("w", 60)

    assert detect_sections(text)[0].name != "preamble"


def test_a_long_line_is_not_a_heading():
    text = "Introduction to the problem of ledgers in modern systems and how they fail\n" + words("w", 60)

    assert [s.name for s in detect_sections(text)] == ["preamble"]


# ── offsets: the property a chunk_search depends on ─────────────────────────


def test_every_chunk_matches_the_text_at_its_own_offsets():
    """A chunk that points at the wrong span misreports section and page."""
    for c in chunk():
        assert DOC[c.start:c.end] == c.text


def test_offsets_are_document_local_not_section_local():
    """Slicing a section while recording document offsets is the failure mode.

    It is invisible on the first section, because there the two coincide; it
    shows up as chunks of a later section carrying text from an earlier one.
    """
    chunks = chunk()
    methods = [c for c in chunks if c.section == "method"]

    assert methods, "fixture should produce method chunks"
    assert all(c.text.split()[0].startswith("beta") for c in methods)


# ── boundaries and size ─────────────────────────────────────────────────────


def test_a_chunk_never_crosses_a_section_boundary():
    """Each section's fixture words share a prefix; a chunk holding two of them
    means the boundary was crossed."""
    for c in chunk():
        if c.section == "abstract":
            continue  # prose, not generated from a single prefix
        prefixes = {w.rstrip("0123456789") for w in c.text.split()}
        assert len(prefixes) == 1, f"chunk mixes sections: {prefixes}"


def test_chunks_overlap_by_the_configured_amount():
    chunks = [c for c in chunk() if c.section == "introduction"]

    first, second = set(chunks[0].text.split()), set(chunks[1].text.split())
    assert len(first & second) == 40


def test_no_chunk_exceeds_the_embedder_budget():
    """MiniLM truncates at 256 word-pieces; a longer chunk loses its tail silently."""
    for c in chunk():
        assert len(c.text.split()) <= TARGET_WORDS


def test_a_short_tail_is_dropped_rather_than_merged():
    """Merging would push the previous chunk past the embedder's cap."""
    chunks = [c for c in chunk() if c.section == "introduction"]

    assert all(len(c.text.split()) >= 25 for c in chunks)


# ── what is kept and what is dropped ────────────────────────────────────────


def test_the_abstract_is_exactly_one_chunk():
    """It is already a curated summary; splitting it scatters the densest signal."""
    abstracts = [c for c in chunk() if c.section == "abstract"]

    assert len(abstracts) == 1
    assert abstracts[0].text == "This paper studies ledgers."


def test_references_are_excluded_by_default():
    assert not [c for c in chunk() if c.section == "references"]


def test_references_can_be_asked_for():
    kept = [c for c in chunk(include_references=True) if c.section == "references"]

    assert kept, "include_references=True should keep them"


def test_the_preamble_is_dropped():
    """Authors, affiliations and copyright notices are not the paper."""
    assert not [c for c in chunk() if c.section == "preamble"]


def test_an_appendix_is_excluded_by_default():
    text = build(("Abstract", "Short."), ("Appendix A", words("a", 200)))

    assert not [c for c in chunk(text=text) if c.section == "appendix"]


def test_acknowledgements_are_excluded_by_default():
    """Measured on a real paper: author lists and funders outranked the method.

    A query about the paper's own subject returned the acknowledgements section
    in two of the top three slots. They match queries about people and answer
    none of them, which is the same reason `references` is dropped.
    """
    text = build(
        ("Abstract", "Short."),
        ("Methods", words("m", 200)),
        ("Acknowledgements", words("thanks", 200)),
    )

    sections = {c.section for c in chunk(text=text)}

    assert "acknowledgements" not in sections
    assert "method" in sections, "the rest of the paper must survive"


def test_funding_is_the_same_section_as_acknowledgements():
    text = build(("Abstract", "Short."), ("Funding", words("grant", 200)))

    assert not [c for c in chunk(text=text) if c.section == "acknowledgements"]


def test_acknowledgements_can_be_asked_for():
    """`include_references` is the switch for all of the back matter."""
    text = build(("Abstract", "Short."), ("Acknowledgements", words("thanks", 200)))

    kept = [c for c in chunk(text=text, include_references=True) if c.section == "acknowledgements"]

    assert kept


# ── identity and degenerate input ───────────────────────────────────────────


def test_ids_are_deterministic_and_unique():
    first = [c.chunk_id for c in chunk()]
    second = [c.chunk_id for c in chunk()]

    assert first == second
    assert len(set(first)) == len(first)
    assert all(cid.startswith("doi:10.1/x::") for cid in first)


def test_chunk_index_is_sequential_across_sections():
    assert [c.index for c in chunk()] == list(range(len(chunk())))


@pytest.mark.parametrize("text", ["", "   ", "\n\n\n"])
def test_an_empty_document_yields_nothing(text):
    assert chunk(text=text) == []


def test_a_document_without_headings_is_dropped_entirely():
    """Everything lands in the preamble, which is not content."""
    assert chunk(text=words("w", 500)) == []


# ── cost ────────────────────────────────────────────────────────────────────


def test_a_long_document_chunks_in_linear_time():
    """Guards against an accidental quadratic scan over a 40k-word body."""
    text = build(("Abstract", "Short."), ("1. Introduction", words("w", 40_000)))

    started = time.perf_counter()
    chunks = chunk(text=text)
    elapsed = time.perf_counter() - started

    assert len(chunks) > 100
    assert elapsed < 5.0, f"took {elapsed:.1f}s — looks quadratic"
