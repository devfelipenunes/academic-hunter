"""Tests for numeric claim extraction and layer-3 verification."""

import json

from academic_hunter.core.writing import (
    extract_claims,
    index_results,
    summarize_numbers,
    verify_numbers,
)


# ── extraction ───────────────────────────────────────────────────────────────


def test_extracts_percentage():
    claims = extract_claims("Overlap of 92.7% was observed.")
    assert [c.kind for c in claims] == ["percent"]
    assert claims[0].value == 92.7


def test_extracts_correlation_in_markdown_math():
    claims = extract_claims(r"The ranking shifted ($\rho = 0.968$) noticeably.")
    assert claims[0].kind == "correlation"
    assert claims[0].value == 0.968


def test_extracts_negative_correlation():
    claims = extract_claims(r"Domains diverge ($\rho = -0.746$).")
    assert claims[0].value == -0.746


def test_extracts_p_value():
    claims = extract_claims("This is significant (p = 0.012).")
    assert claims[0].kind == "pvalue"
    assert claims[0].value == 0.012


def test_extracts_paper_count():
    claims = extract_claims("The run retrieved 1,538 papers in total.")
    assert claims[0].kind == "count"
    assert claims[0].value == 1538.0


def test_count_handles_thousands_separator():
    claims = extract_claims("We identified 2,332 papers.")
    assert claims[0].value == 2332.0


def test_a_percentage_is_not_also_reported_as_a_decimal():
    """Each position is claimed once, by the most specific pattern."""
    claims = extract_claims("An overlap of 92.7% was measured.")
    assert len(claims) == 1


def test_claims_carry_their_sentence():
    text = "The ablation reached 92.7% overlap. Another finding follows."
    context = extract_claims(text)[0].context
    assert "ablation reached" in context
    assert "Another finding" not in context


def test_claims_are_ordered_by_position():
    claims = extract_claims("First 10 papers, then 92.7% overlap.")
    assert [c.offset for c in claims] == sorted(c.offset for c in claims)


def test_no_numbers_yields_no_claims():
    assert extract_claims("This sentence has no figures in it.") == []


def test_section_references_are_not_treated_as_findings():
    """Structural pointers are not results.

    Including them produced 131 bogus matches on a real manuscript, because
    "3.13" was compared against 0.0313.
    """
    text = "As shown in §3.13 and Table 2.1, and in Section 4.2, this holds."
    assert extract_claims(text) == []


def test_section_filter_does_not_swallow_real_findings():
    """The filter must only claim the pointer, not the sentence around it."""
    claims = extract_claims("In §3.13 we report 92.7% overlap.")
    assert [c.kind for c in claims] == ["percent"]


# ── indexing ─────────────────────────────────────────────────────────────────


def test_index_collects_nested_numbers(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({
        "results": [{"mean": 3.261, "pass_35": 281}, {"std": 2.231}],
        "config": {"limit": 50},
    }))
    known = index_results(tmp_path)
    assert 3.261 in known
    assert 281.0 in known
    assert 50.0 in known


def test_index_ignores_booleans(tmp_path):
    """True is an int in Python and would otherwise pollute the index with 1.0."""
    (tmp_path / "a.json").write_text(json.dumps({"flag": True, "other": False}))
    assert index_results(tmp_path) == set()


def test_index_skips_malformed_files_without_failing(tmp_path):
    (tmp_path / "good.json").write_text(json.dumps({"x": 42}))
    (tmp_path / "bad.json").write_text("{not json at all")
    known = index_results(tmp_path)
    assert 42.0 in known


def test_index_of_missing_directory_is_empty(tmp_path):
    assert index_results(tmp_path / "nope") == set()


# ── verification ─────────────────────────────────────────────────────────────


def _claims(text):
    return extract_claims(text)


def test_matched_when_the_value_is_present():
    results = verify_numbers(_claims("Overlap was 92.7%."), {92.7, 1.0})
    assert results[0].status == "MATCHED"


def test_percentage_matches_its_fraction_form():
    """93.0% in prose and 0.93 in JSON are the same quantity."""
    results = verify_numbers(_claims("Reached 93.0% exclusivity."), {0.93})
    assert results[0].status in ("MATCHED", "CLOSE")


def test_matches_when_the_file_holds_more_precision():
    """0.968 in the text and 0.9679 in the file are the same figure."""
    results = verify_numbers(_claims("A value of 0.968 was measured."), {0.9679})
    assert results[0].status == "MATCHED"
    assert results[0].matched_value == 0.9679


def test_does_not_match_a_different_figure_at_the_same_precision():
    """The regression that motivated precision-based comparison.

    Under the original 1%-relative tolerance a fabricated 87.3% matched the
    file's 0.871 — because 237 of the 338 indexed values sit within 1% of some
    other value, the check confirmed 191 of 191 claims.
    """
    results = verify_numbers(
        _claims("A separate run achieved 87.3% overlap."), {0.871, 0.927}
    )
    assert results[0].status == "UNSOURCED"


def test_real_figure_still_matches_alongside_a_fabricated_one():
    """Tightening must not break the true positives."""
    results = verify_numbers(
        _claims("The ablation reached 92.7% overlap. Another run got 87.3%."),
        {0.871, 0.927},
    )
    statuses = {r.claim.value: r.status for r in results}
    assert statuses[92.7] == "MATCHED"
    assert statuses[87.3] == "UNSOURCED"


def test_unsourced_when_nothing_is_close():
    results = verify_numbers(_claims("The figure was 92.7%."), {12.5, 300.0})
    assert results[0].status == "UNSOURCED"
    assert results[0].matched_value is None


def test_empty_index_reports_unsourced_not_an_error():
    results = verify_numbers(_claims("A value of 92.7%."), set())
    assert results[0].status == "UNSOURCED"
    assert "no result files" in results[0].evidence


def test_summarize_counts_each_status():
    results = verify_numbers(
        _claims("We saw 92.7% overlap and 55.5% growth."), {92.7}
    )
    counts = summarize_numbers(results)
    assert counts["MATCHED"] == 1
    assert counts["UNSOURCED"] == 1


def test_each_claim_is_judged_independently():
    """One unsourced figure must not mask a sourced one."""
    results = verify_numbers(
        _claims("Value 92.7% and value 11.1%."), {92.7}
    )
    statuses = {r.claim.value: r.status for r in results}
    assert statuses[92.7] == "MATCHED"
    assert statuses[11.1] == "UNSOURCED"
