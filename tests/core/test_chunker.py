"""Tests for the full-text chunker.

Pure arithmetic over a string: no PDF, no model, no I/O.
"""

import time

import pytest

from academic_hunter.core.fulltext import chunk_document, detect_sections
from academic_hunter.core.fulltext.chunker import TARGET_WORDS
from academic_hunter.core.ports.fulltext import ExtractedDocument, PageSpan


def build(*sections, preamble="Journal of Examples\nA. Author\n"):
    """A document from ``(heading, body)`` pairs."""
    parts = [preamble]
    for heading, body in sections:
        parts.append(f"{heading}\n{body}\n")
    return "\n".join(parts)


def words(prefix, count):
    return " ".join(f"{prefix}{i}" for i in range(count))


DOC = build(
    ("Abstract", "This paper studies ledgers."),
    ("1. Introduction", words("alpha", 300)),
    ("2. Methods", words("beta", 400)),
    ("References", words("gamma", 500)),
)


def chunk(path="doi:10.1/x", text=DOC, **kwargs):
    return chunk_document(ExtractedDocument(text=text, page_count=9), path, **kwargs)


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


def test_chunks_keep_pdf_page_ranges_from_extracted_text():
    text = "Abstract\na b c d e f g h"
    doc = ExtractedDocument(
        text=text,
        page_count=2,
        page_spans=[PageSpan(start=9, end=16, page=4), PageSpan(start=17, end=24, page=5)],
    )

    chunks = chunk_document(
        doc, "doi:10.1/pages", target_words=4, overlap_words=0, min_chunk_words=1
    )

    assert [(c.page_start, c.page_end) for c in chunks] == [(4, 4), (5, 5)]


def test_chunk_crossing_a_pdf_page_boundary_cites_both_pages():
    text = "Abstract\na b c d e f"
    doc = ExtractedDocument(
        text=text,
        page_count=2,
        page_spans=[PageSpan(start=9, end=13, page=2), PageSpan(start=14, end=20, page=3)],
    )

    chunks = chunk_document(doc, "doi:10.1/crossing", target_words=6, overlap_words=0)

    assert len(chunks) == 1
    assert (chunks[0].page_start, chunks[0].page_end) == (2, 3)


def test_a_chunk_never_crosses_a_section_boundary():
    """Each section's fixture words share a prefix; a chunk holding two of them
    means the boundary was crossed."""
    for c in chunk():
        if c.section == "abstract":
            continue
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


def test_a_span_of_exactly_one_window_yields_one_chunk():
    """The tail left over was the overlap the first chunk had just written.

    At exactly ``target_words`` the loop advanced by ``step``, found
    ``overlap_words`` still to cover, and emitted them as a second chunk whose
    whole text already sat inside the first. The same passage indexed twice, so
    one source could fill two of a query's result slots — and a reader shown
    both would have no way to tell they were the same text.
    """
    body = words("a", TARGET_WORDS)
    text = build(("Abstract", body), ("Introduction", words("b", 200)))

    abstracts = [c for c in chunk(text=text) if c.section == "abstract"]

    assert len(abstracts) == 1
    assert abstracts[0].text == body


def test_no_chunk_is_wholly_contained_in_another():
    """Every chunk has to add text; a contained one adds none."""
    chunks = chunk()

    for outer in chunks:
        for inner in chunks:
            if inner is not outer:
                assert inner.text not in outer.text, (
                    f"chunk {inner.chunk_id} is already inside {outer.chunk_id}"
                )


def test_dropping_the_duplicate_tail_loses_no_words():
    """The guard stops before a window that is entirely inside its predecessor,
    so nothing that used to be indexed stops being indexed."""
    body = words("a", TARGET_WORDS)
    text = build(("Abstract", body), ("Introduction", words("b", 200)))

    indexed = {
        word
        for c in chunk(text=text)
        if c.section == "abstract"
        for word in c.text.split()
    }

    assert indexed == set(body.split())


def test_a_short_abstract_is_exactly_one_chunk():
    """It fits in one window, so splitting it would scatter the densest signal."""
    abstracts = [c for c in chunk() if c.section == "abstract"]

    assert len(abstracts) == 1
    assert abstracts[0].text == "This paper studies ledgers."


def test_a_long_abstract_keeps_every_word():
    """An abstract longer than one window used to lose its tail in silence.

    `whole_span` forced it into a single window and then broke the loop, so the
    remainder was never indexed — with nothing counting it, and the ingest still
    reporting the fetch as "obtained". Measured on a 300-word abstract: 180
    indexed, 120 gone.
    """
    body = words("a", 300)
    text = build(("Abstract", body), ("Introduction", words("b", 200)))

    indexed = {
        word
        for c in chunk(text=text)
        if c.section == "abstract"
        for word in c.text.split()
    }
    missing = [w for w in body.split() if w not in indexed]

    assert not missing, f"{len(missing)} of the abstract's words were never indexed"


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


def test_a_long_document_chunks_in_linear_time():
    """Guards against an accidental quadratic scan over a 40k-word body."""
    text = build(("Abstract", "Short."), ("1. Introduction", words("w", 40_000)))

    started = time.perf_counter()
    chunks = chunk(text=text)
    elapsed = time.perf_counter() - started

    assert len(chunks) > 100
    assert elapsed < 5.0, f"took {elapsed:.1f}s — looks quadratic"
