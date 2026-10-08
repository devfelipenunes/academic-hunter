"""Tests for citation extraction and layer-1 existence verification."""


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


def test_context_survives_a_decimal_point():
    """A sentence does not end at a decimal point.

    The window was found by breaking the text at `[.!?]` indiscriminately, so
    `92.7%` was cut at the dot and the context shown to the reader began at
    `7% overlap` — the figure the citation is supposed to support, truncated.
    """
    text = "The ablation reached 92.7% overlap [@echo2024]. Another sentence follows."
    cites = extract_citations(text)

    assert "92.7% overlap" in cites[0].context
    assert "Another sentence follows" not in cites[0].context


def test_handles_keys_with_hyphens():
    """The project uses package names like 'sentence-transformers' as keys."""
    cites = extract_citations("See [@sentence-transformers] for details.")
    assert [c.key for c in cites] == ["sentence-transformers"]


def test_a_pandoc_locator_is_not_part_of_the_key():
    """`[@echo2024, p. 33]` cites `echo2024`, not a key spelled `echo2024, p. 33`.

    The key pattern ran to the closing bracket, so every locator became part of
    the key — and a key that exists in the bibliography was reported as one that
    does not.
    """
    cites = extract_citations("See [@echo2024, p. 33] for the detail.")
    assert [c.key for c in cites] == ["echo2024"]


def test_a_locator_survives_a_multi_key_bracket():
    cites = extract_citations("Prior work [@a2024, ch. 2; @b2025, pp. 10-12] shows this.")
    assert [c.key for c in cites] == ["a2024", "b2025"]


def test_ignores_text_without_citations():
    assert extract_citations("No citations here at all.") == []


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


def test_an_indented_closing_brace_still_parses():
    """`.bib` files are written indented; requiring `}` at column 0 lost them.

    The pattern anchored the entry's end to a brace at the start of a line, so
    an entry whose closing brace carries the same indentation as its fields —
    which is how the exporter writes them — parsed to nothing at all.
    """
    indented = (
        "@article{e2024,\n"
        "  title = {Echo Chambers},\n"
        "  doi = {10.1/e},\n"
        "  }\n"
    )
    assert parse_bibtex_entries(indented)["e2024"]["doi"] == "10.1/e"


def test_entries_and_keys_agree_on_what_is_in_the_file():
    """The two readers must not disagree about which entries exist.

    `parse_bibtex_keys` scanned one way and `parse_bibtex_entries` another, so a
    key could be found by one and not the other. The mismatch is what made a
    citation verifiable and unverifiable depending on which check ran.
    """
    single_line = "@article{e2024, title = {Echo}, doi = {10.1/e}}"
    multiline = BIB

    for bibliography in (single_line, multiline):
        assert set(parse_bibtex_entries(bibliography)) == parse_bibtex_keys(bibliography)


def test_a_braced_field_may_contain_commas_and_braces():
    """Splitting fields on commas breaks the moment a title has one."""
    bib = (
        "@article{e2024,\n"
        "  title = {Echo, Chambers, and the {Nested} Case},\n"
        "  author = {Springer, Anna and Kotha, Suhas},\n"
        "  year = {2024}\n"
        "}\n"
    )
    entry = parse_bibtex_entries(bib)["e2024"]
    assert entry["title"] == "Echo, Chambers, and the {Nested} Case"
    assert entry["author"] == "Springer, Anna and Kotha, Suhas"
    assert entry["year"] == "2024"


def test_a_quoted_field_is_read_to_its_closing_quote():
    """BibTeX allows `"…"` values as well as `{…}`."""
    bib = '@article{e2024, title = "Echo Chambers", year = {2024}}'
    assert parse_bibtex_entries(bib)["e2024"]["title"] == "Echo Chambers"


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
