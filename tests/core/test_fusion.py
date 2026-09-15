"""Tests for the score fusion that produces ``Relevance_Score``.

The rule was replaced after the judged collection showed the old one measured
worse than either of its own inputs. These tests pin the property that made the
difference — magnitudes survive the combination — and the degenerate cases that
would silently empty a run.
"""

import pytest

from academic_hunter.core.nlp import fuse_scores, percentile_ranks


def fuse(kw, sem, strategy="weighted_norm", weights=None):
    """Call the shipped fusion — never a reimplementation of it."""
    return fuse_scores(kw, sem, strategy=strategy, weights=weights)


# ── the property that motivated the change ──────────────────────────────────


def test_paper_strong_on_both_outranks_paper_weak_on_both():
    scores = fuse(kw=[10.0, 1.0], sem=[0.9, 0.1])

    assert scores[0] > scores[1]
    assert scores[0] == pytest.approx(10.0)
    assert scores[1] == pytest.approx(0.0)


def test_strong_signal_is_not_dragged_down_by_a_middling_one():
    """The property the rank-geometric mean lacked.

    Under ``sqrt(rank_kw * rank_sem)`` both signals are flattened to percentile
    ranks before combining, so a paper far ahead on one signal and mid-pack on
    the other becomes indistinguishable from one mediocre on both. That is the
    measurement that motivated replacing the rule.
    """
    kw = [100.0, 5.0, 4.0, 3.0]
    sem = [0.5, 0.5, 0.5, 0.5]  # embedding ties, so keyword decides

    scores = fuse(kw, sem)

    assert scores[0] > scores[1] > scores[2] > scores[3]


def test_magnitudes_survive_normalisation():
    """Normalisation removes offset and scale, not the spacing itself."""
    scores = fuse(kw=[0.0, 1.0, 3.0], sem=[0.0, 0.0, 0.0])

    assert scores[2] - scores[1] == pytest.approx(2 * (scores[1] - scores[0]))


def test_scores_stay_within_the_reported_scale():
    scores = fuse(kw=[0.0, 50.0, -3.0], sem=[0.0, 1.0, 0.2])

    assert min(scores) >= 0.0
    assert max(scores) <= 10.0


# ── weights ─────────────────────────────────────────────────────────────────


def test_default_weights_favour_keyword():
    """Default is 70/30 keyword/embedding — the ratio the mode labels claim."""
    scores = fuse(kw=[0.0, 10.0], sem=[10.0, 0.0])

    assert scores[1] > scores[0], "the keyword-strong document must win"
    assert scores[1] == pytest.approx(7.0)
    assert scores[0] == pytest.approx(3.0)


def test_weights_are_configurable():
    scores = fuse(kw=[0.0, 10.0], sem=[10.0, 0.0],
                  weights={"keyword": 0.0, "embedding": 1.0})

    assert scores[0] == pytest.approx(10.0)
    assert scores[1] == pytest.approx(0.0)


def test_zero_weights_fall_back_to_keyword_instead_of_dividing_by_zero():
    """A degenerate config must not produce zeros and empty the run."""
    scores = fuse([0.0, 10.0], [10.0, 0.0], weights={"keyword": 0, "embedding": 0})

    assert scores[1] > scores[0]


def test_weights_are_normalised_by_their_sum():
    """Only the ratio matters, so unnormalised weights behave the same."""
    kw, sem = [0.0, 10.0], [10.0, 0.0]

    a = fuse(kw, sem, weights={"keyword": 0.7, "embedding": 0.3})
    b = fuse(kw, sem, weights={"keyword": 7, "embedding": 3})

    assert a == pytest.approx(b)


def test_partial_weights_override_only_what_they_name():
    """Missing keys keep their defaults rather than collapsing to zero.

    Asserted as a ratio: naming only ``embedding`` leaves ``keyword`` at its
    0.7 default, so the keyword-only document gets 0.7 of what the
    embedding-only document gets, whatever the shared total works out to.
    """
    scores = fuse([0.0, 10.0], [10.0, 0.0], weights={"embedding": 1.0})

    assert scores[1] / scores[0] == pytest.approx(0.7)


# ── strategy selection and degenerate cases ─────────────────────────────────


def test_rank_geometric_strategy_reproduces_the_old_rule():
    """The superseded rule stays available so earlier runs are reproducible."""
    scores = fuse([1.0, 2.0, 3.0], [3.0, 2.0, 1.0], strategy="rank_geometric")

    # Symmetric inputs: the extremes tie, the middle paper peaks.
    assert scores[0] == pytest.approx(scores[2])
    assert scores[1] == pytest.approx(5.0)


def test_constant_signals_tie_at_the_top_not_the_bottom():
    """With nothing to rank, papers tie at 10 — not 0.

    Normalising a constant yields zero, and a zero reads as "irrelevant" at the
    threshold filter, which would silently empty the run. This is the same
    failure mode as the old early-return on fewer than two papers.
    """
    scores = fuse([5.0, 5.0, 5.0], [0.4, 0.4, 0.4])

    assert list(scores) == [10.0, 10.0, 10.0]


def test_a_flat_signal_with_no_evidence_does_not_tie_at_the_top():
    """Absent evidence is not the same as equal evidence.

    Every raw score is zero, which is what a ranking query whose terms are in no
    paper produces. `_minmax` already answers this — "a signal that does not vary
    carries no ordering information, so it should contribute nothing" — and the
    caller turned its zeros into 10.0, the top of the scale, approving the whole
    corpus at the threshold.
    """
    scores = fuse([0.0, 0.0], [0.0, 0.0], weights={"keyword": 1.0, "embedding": 0.0})

    assert list(scores) == [0.0, 0.0]


def test_a_flat_signal_matching_nothing_is_not_evidence_even_if_unweighted():
    """The embedding is weighted zero here, so its value cannot be the evidence."""
    scores = fuse([0.0, 0.0], [0.4, 0.4], weights={"keyword": 1.0, "embedding": 0.0})

    assert list(scores) == [0.0, 0.0]


def test_one_constant_signal_still_ranks_by_the_other():
    """A flat embedding must not flatten the keyword ordering."""
    scores = fuse([1.0, 2.0, 3.0], [0.5, 0.5, 0.5])

    assert scores[2] > scores[1] > scores[0]


def test_single_paper_takes_the_top_of_the_scale():
    scores = fuse([3.0], [0.2])

    assert scores == [10.0]


def test_empty_input_returns_empty():
    assert fuse([], []) == []


def test_misaligned_inputs_raise():
    """Silently zipping mismatched signals would drop papers."""
    with pytest.raises(ValueError, match="must align"):
        fuse([1.0, 2.0], [0.5])


# ── percentile ranks ────────────────────────────────────────────────────────


def test_percentile_ranks_span_zero_to_one():
    ranks = percentile_ranks([30.0, 10.0, 20.0])

    assert ranks == [1.0, 0.0, 0.5]


def test_percentile_ranks_of_single_value_is_top():
    """No distribution to rank against, so the value is trivially the top."""
    assert percentile_ranks([7.0]) == [1.0]


def test_percentile_ranks_of_empty_list():
    assert percentile_ranks([]) == []
