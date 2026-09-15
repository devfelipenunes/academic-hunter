"""Tests for the retrieval metrics.

These pin the definitions, because every one of them has a plausible variant
that differs by a constant or a denominator — and a metric that is off by a
constant is a metric that will "show" an improvement that isn't there.
"""

import math

import pytest

from academic_hunter.core.evaluation import (
    average_precision,
    dcg_at_k,
    evaluate_ranking,
    mean_metrics,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

# Three relevant documents at grades 3, 2, 1, plus one judged irrelevant.
REL = {"a": 3, "b": 2, "c": 1, "d": 0}


# ── DCG ─────────────────────────────────────────────────────────────────────


def test_dcg_first_position_is_undiscounted():
    """Position 1 divides by log2(2) == 1, so its gain passes through whole."""
    # grade 3 -> gain 2^3 - 1 == 7
    assert dcg_at_k(["a"], REL, 1) == pytest.approx(7.0)


def test_dcg_applies_log2_discount():
    """Position 2 halves the gain."""
    expected = 7.0 / math.log2(2) + 3.0 / math.log2(3)
    assert dcg_at_k(["a", "b"], REL, 2) == pytest.approx(expected)


def test_dcg_ignores_irrelevant_and_unjudged():
    """Grade 0 and unjudged documents contribute nothing."""
    assert dcg_at_k(["d", "zzz"], REL, 2) == 0.0


def test_dcg_linear_gain_option():
    """Linear gain uses the raw grade instead of 2^grade - 1."""
    assert dcg_at_k(["a"], REL, 1, linear_gain=True) == pytest.approx(3.0)


def test_dcg_zero_k_is_zero():
    assert dcg_at_k(["a"], REL, 0) == 0.0


# ── nDCG ────────────────────────────────────────────────────────────────────


def test_ndcg_is_one_for_the_ideal_ranking():
    """Perfect ordering scores exactly 1.0."""
    assert ndcg_at_k(["a", "b", "c"], REL, 3) == pytest.approx(1.0)


def test_ndcg_penalises_inverted_grades():
    """A grade-1 document ranked above a grade-3 one must score below 1.0."""
    inverted = ndcg_at_k(["c", "b", "a"], REL, 3)

    assert inverted < 1.0
    assert inverted > 0.0


def test_ndcg_is_monotonic_in_ranking_quality():
    """Better orderings score higher — the property the whole exercise rests on."""
    best = ndcg_at_k(["a", "b", "c"], REL, 3)
    middle = ndcg_at_k(["b", "a", "c"], REL, 3)
    worst = ndcg_at_k(["c", "b", "a"], REL, 3)

    assert best > middle > worst


def test_ndcg_normalisation_uses_ideal_at_k():
    """The ideal list is truncated to k, so a perfect top-k scores 1.0."""
    assert ndcg_at_k(["a", "b"], REL, 2) == pytest.approx(1.0)


def test_ndcg_without_relevant_documents_is_zero():
    """A query with nothing relevant has no ideal ranking to normalise against."""
    assert ndcg_at_k(["a", "b"], {"a": 0, "b": 0}, 5) == 0.0


def test_ndcg_counts_unjudged_as_not_relevant():
    """Unjudged documents must not be credited as relevant."""
    assert ndcg_at_k(["zzz", "yyy"], REL, 2) == 0.0


# ── recall ──────────────────────────────────────────────────────────────────


def test_recall_at_k_counts_judged_relevant():
    """2 of the 3 relevant documents found in the top 2."""
    assert recall_at_k(["a", "b"], REL, 2) == pytest.approx(2 / 3)


def test_recall_at_k_is_capped_by_k():
    """A single position can never recall three documents."""
    assert recall_at_k(["a"], REL, 1) == pytest.approx(1 / 3)


def test_recall_full_when_all_relevant_retrieved():
    assert recall_at_k(["c", "b", "a"], REL, 3) == pytest.approx(1.0)


def test_recall_threshold_excludes_low_grades():
    """With threshold 2, the grade-1 document no longer counts as relevant."""
    # Only 'a' and 'b' qualify, and both are retrieved.
    assert recall_at_k(["a", "b"], REL, 2, threshold=2) == pytest.approx(1.0)


def test_recall_without_relevant_documents_is_zero():
    assert recall_at_k(["a"], {"a": 0}, 5) == 0.0


def test_recall_zero_k_is_zero():
    assert recall_at_k(["a"], REL, 0) == 0.0


# ── precision ───────────────────────────────────────────────────────────────


def test_precision_divides_by_k_not_by_returned_count():
    """Returning 1 document when 5 were asked for is not perfect precision.

    This is the variant that silently inflates a retriever with poor coverage.
    """
    assert precision_at_k(["a"], REL, 5) == pytest.approx(1 / 5)


def test_precision_counts_relevant_in_top_k():
    assert precision_at_k(["a", "d", "b"], REL, 3) == pytest.approx(2 / 3)


def test_precision_zero_k_is_zero():
    assert precision_at_k(["a"], REL, 0) == 0.0


# ── rank-based ──────────────────────────────────────────────────────────────


def test_reciprocal_rank_of_first_hit():
    assert reciprocal_rank(["d", "b", "a"], REL) == pytest.approx(1 / 2)


def test_reciprocal_rank_of_top_hit_is_one():
    assert reciprocal_rank(["a", "b"], REL) == pytest.approx(1.0)


def test_reciprocal_rank_without_hits_is_zero():
    assert reciprocal_rank(["d", "zzz"], REL) == 0.0


def test_average_precision_is_normalised_by_total_relevant():
    """Finding only the easy documents does not earn a perfect AP."""
    # 'a' at rank 1 -> 1/1; 'b' at rank 3 -> 2/3. Missing 'c' entirely.
    # AP = (1/1 + 2/3) / 3, NOT / 2.
    assert average_precision(["a", "d", "b"], REL) == pytest.approx((1.0 + 2 / 3) / 3)


def test_average_precision_perfect_ranking_is_one():
    assert average_precision(["a", "b", "c"], REL) == pytest.approx(1.0)


def test_average_precision_without_relevant_is_zero():
    assert average_precision(["d"], {"d": 0}) == 0.0


# ── aggregate ───────────────────────────────────────────────────────────────


def test_evaluate_ranking_reports_all_requested_cutoffs():
    metrics = evaluate_ranking(["a", "b", "c"], REL, ks=[1, 3])

    assert set(metrics) == {
        "ndcg@1", "ndcg@3",
        "recall@1", "recall@3",
        "precision@1", "precision@3",
        "mrr", "ap",
    }


def test_evaluate_ranking_ignores_non_positive_cutoffs():
    metrics = evaluate_ranking(["a"], REL, ks=[0, -5, 1])

    assert "ndcg@1" in metrics
    assert "ndcg@0" not in metrics


def test_mean_metrics_averages_key_by_key():
    mean = mean_metrics([{"ndcg@10": 1.0}, {"ndcg@10": 0.0}])

    assert mean["ndcg@10"] == pytest.approx(0.5)


def test_mean_metrics_of_nothing_is_empty():
    """A run with no judged queries has no mean — report it as absent."""
    assert mean_metrics([]) == {}


def test_mean_metrics_only_averages_shared_keys():
    """Keys missing from some entries are dropped rather than treated as zero."""
    mean = mean_metrics([{"a": 1.0, "b": 0.0}, {"a": 0.0}])

    assert mean == {"a": 0.5}


# ── a ranking lists a document once ─────────────────────────────────────────


def test_a_repeated_document_is_not_a_second_hit_in_average_precision():
    """Counting it twice made AP exceed its own maximum.

    `average_precision(["a", "a"], {"a": 1})` returned **2.0**. A metric that can
    go above 1 is one nobody reads correctly: "AP improved to 1.4" does not look
    like an error, it looks like a result.
    """
    assert average_precision(["a", "a"], {"a": 1}) == 1.0


def test_a_repeated_document_adds_no_gain_of_its_own():
    """It occupies a slot — and discounting that is correct — but scores nothing.

    Compared against an unrelated document in the same position, so the assertion
    is about the repeat's own contribution and not about the ranks it shifts.
    """
    duplicated = dcg_at_k(["a", "a", "b"], {"a": 1, "b": 1}, 3)
    unrelated = dcg_at_k(["a", "z", "b"], {"a": 1, "b": 1}, 3)

    assert duplicated == unrelated


def test_a_repeated_document_cannot_push_ndcg_above_one():
    assert ndcg_at_k(["a", "a"], {"a": 1}, 2) == 1.0


def test_skipping_the_repeat_does_not_shift_what_follows_it():
    """The document after the duplicate still sits at its own rank.

    Deduplicating by *removing* the repeat would move `b` from position 3 to 2 and
    inflate every metric that discounts by rank; skipping it in place does not.
    """
    assert average_precision(["a", "a", "b"], {"a": 1, "b": 1}) == pytest.approx(5 / 6)


def test_a_ranking_without_repeats_is_untouched():
    """Both relevant documents at the top is a perfect ranking, duplicate or not."""
    assert average_precision(["a", "b"], {"a": 1, "b": 1}) == 1.0
