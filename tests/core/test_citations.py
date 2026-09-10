"""Tests for citation extraction and layer-1 existence verification."""

import pytest

from academic_hunter.core.writing import (
    ExistenceProbes,
    extract_citations,
    parse_bibtex_entries,
    parse_bibtex_keys,
    summarize_citations,
    verify_existence,
)

BIB = """
@article{echo2024,
  title = {Repetition Improves Language Model Embeddings},
  author = {Springer and Kotha},
  year = {2024},
  doi = {10.48550/arXiv.2402.15449},
  journal = {arXiv preprint}
}

@inproceedings{sgpt2022,
  title = {Multilingual Autoregressive},
  author = {Muennighoff},
  year = {2022}
}
"""


# ── extraction ───────────────────────────────────────────────────────────────


def test_extracts_single_citation():
    cites = extract_citations("As shown by Springer [@echo2024], repetition helps.")
    assert [c.key for c in cites] == ["echo2024"]


def test_extracts_multiple_keys_from_one_bracket():
    """Each key in [@a; @b] must be verified independently."""
    cites = extract_citations("Prior work [@queenbee2026; @hybridagentic2026] shows this.")
    assert [c.key for c in cites] == ["queenbee2026", "hybridagentic2026"]


def test_extracts_several_citations_in_a_row():
    text = "First [@a2024]. Then [@b2025]. Finally [@c2026]."
    assert [c.key for c in extract_citations(text)] == ["a2024", "b2025", "c2026"]


def test_captures_the_containing_sentence_as_context():
    text = "Weight-Bleeding changes the ranking [@echo2024]. Another sentence follows."
    cites = extract_citations(text)
    assert "Weight-Bleeding changes the ranking" in cites[0].context
    assert "Another sentence follows" not in cites[0].context


def test_handles_keys_with_hyphens():
    """The project uses package names like 'sentence-transformers' as keys."""
    cites = extract_citations("See [@sentence-transformers] for details.")
    assert [c.key for c in cites] == ["sentence-transformers"]


def test_ignores_text_without_citations():
    assert extract_citations("No citations here at all.") == []


# ── bibtex parsing ───────────────────────────────────────────────────────────


def test_parse_keys():
    assert parse_bibtex_keys(BIB) == {"echo2024", "sgpt2022"}


def test_parse_entries_captures_doi_and_title():
    entries = parse_bibtex_entries(BIB)
    assert entries["echo2024"]["doi"] == "10.48550/arXiv.2402.15449"
    assert "Repetition Improves" in entries["echo2024"]["title"]
    assert entries["echo2024"]["type"] == "article"
    assert entries["sgpt2022"]["type"] == "inproceedings"
    assert "doi" not in entries["sgpt2022"]


def test_parse_entries_tolerates_malformed_input():
    """Unparseable bibliography yields no evidence — never a false accusation."""
    assert parse_bibtex_entries("this is not bibtex {{{") == {}


# ── verification ─────────────────────────────────────────────────────────────


def _cites(text="See [@k2024]."):
    return extract_citations(text)


def test_verified_when_bibliography_confirms():
    probes = ExistenceProbes(in_bibliography=lambda key: True)
    results = verify_existence(_cites(), probes)
    assert results[0].verdict == "VERIFIED"
    assert "bibliography" in results[0].evidence


def test_not_found_when_key_absent_from_bibliography():
    probes = ExistenceProbes(in_bibliography=lambda key: False)
    results = verify_existence(_cites(), probes)
    assert results[0].verdict == "NOT_FOUND"
    assert "not in the bibliography" in results[0].evidence


def test_not_found_when_doi_does_not_resolve():
    probes = ExistenceProbes(
        in_bibliography=lambda key: True,
        resolve_doi=lambda key: "10.1/nonexistent",
        doi_resolves=lambda doi: False,
    )
    results = verify_existence(_cites(), probes)
    assert results[0].verdict == "NOT_FOUND"
    assert "does not resolve" in results[0].evidence


def test_verified_when_all_available_probes_agree():
    probes = ExistenceProbes(
        in_bibliography=lambda key: True,
        resolve_doi=lambda key: "10.1/real",
        doi_resolves=lambda doi: True,
        in_corpus=lambda key: True,
    )
    results = verify_existence(_cites(), probes)
    assert results[0].verdict == "VERIFIED"
    assert "bibliography" in results[0].evidence and "DOI" in results[0].evidence


def test_unknown_when_no_probe_can_decide():
    """'Could not verify' must never be reported as 'fabricated'."""
    probes = ExistenceProbes(in_bibliography=lambda key: None)
    results = verify_existence(_cites(), probes)
    assert results[0].verdict == "UNKNOWN"
    assert results[0].in_bibliography is None


def test_no_probes_at_all_yields_unknown():
    results = verify_existence(_cites(), ExistenceProbes())
    assert results[0].verdict == "UNKNOWN"


def test_missing_doi_does_not_make_a_citation_fail():
    """A key without a DOI simply skips that check."""
    probes = ExistenceProbes(
        in_bibliography=lambda key: True,
        resolve_doi=lambda key: None,
        doi_resolves=lambda doi: False,
    )
    results = verify_existence(_cites(), probes)
    assert results[0].verdict == "VERIFIED"


def test_corpus_only_check_can_verify():
    probes = ExistenceProbes(in_corpus=lambda key: True)
    assert verify_existence(_cites(), probes)[0].verdict == "VERIFIED"


def test_corpus_absence_does_not_refute():
    """The corpus is a subset of the literature — a real paper may not be indexed.

    Treating absence from the local index as proof of fabrication produced a
    30-of-30 false-positive rate when first run against a real manuscript.
    """
    probes = ExistenceProbes(in_corpus=lambda key: False)
    assert verify_existence(_cites(), probes)[0].verdict == "UNKNOWN"


def test_summarize_counts_by_verdict():
    probes = ExistenceProbes(in_bibliography=lambda key: key != "bad2024")
    results = verify_existence(_cites("See [@good2024] and [@bad2024]."), probes)
    counts = summarize_citations(results)
    assert counts["VERIFIED"] == 1
    assert counts["NOT_FOUND"] == 1


def test_each_citation_reports_independently():
    """One bad key must not mask a good one."""
    probes = ExistenceProbes(in_bibliography=lambda key: key == "good2024")
    results = verify_existence(_cites("[@good2024; @bad2024]"), probes)
    verdicts = {r.key: r.verdict for r in results}
    assert verdicts == {"good2024": "VERIFIED", "bad2024": "NOT_FOUND"}
