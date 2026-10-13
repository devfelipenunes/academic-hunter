"""Tests for the score fusion that produces ``Relevance_Score``.

The rule was replaced after a hand-judged sample showed the old one measured
worse than either of its own inputs. These tests pin the property that made the
difference — magnitudes survive the combination — and the degenerate cases that
would silently empty a run.
"""

import pytest

from academic_hunter.core.nlp import fuse_scores, percentile_ranks, resolve_weights
from academic_hunter.core.nlp.fusion import _minmax


def fuse(kw, sem, strategy="weighted_norm", weights=None):
    """Call the shipped fusion — never a reimplementation of it."""
    return fuse_scores(kw, sem, strategy=strategy, weights=weights)


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
    sem = [0.5, 0.5, 0.5, 0.5]

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


def test_zero_weights_fall_back_at_the_reported_scale():
    """The fallback keeps the [0, 10] scale the docstring promises.

    Ordering alone survives any constant multiplier — doubling every score keeps
    the ranking and breaks every comparison against the threshold.
    """
    scores = fuse([1.0, 2.0, 3.0], [0.0, 0.0, 0.0], weights={"keyword": 0, "embedding": 0})

    assert list(scores) == pytest.approx([0.0, 5.0, 10.0])


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


def test_rank_geometric_strategy_reproduces_the_old_rule():
    """The superseded rule stays available so earlier runs are reproducible."""
    scores = fuse([1.0, 2.0, 3.0], [3.0, 2.0, 1.0], strategy="rank_geometric")

    assert scores[0] == pytest.approx(scores[2])
    assert scores[1] == pytest.approx(5.0)


def test_rank_geometric_with_no_evidence_does_not_tie_at_the_top():
    """Zero evidence is not a ladder.

    With both signals flat, ``percentile_ranks`` resolves the ties by insertion
    order and ``sqrt(a*b)*10`` turns that into ``[0, 3.33, 6.67, 10]``: the last
    paper scores 10 and passes the threshold, and which paper is "last" is the
    order the threads happened to finish in. The superseded rule now reads the
    guard its sibling always had.
    """
    scores = fuse([0.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0], strategy="rank_geometric")

    assert list(scores) == [0.0, 0.0, 0.0, 0.0]


def test_rank_geometric_with_a_flat_signal_and_evidence_ties_at_the_top():
    """A flat non-zero signal carries no ordering, so the papers tie at the top.

    Scoring them at zero instead would read as "irrelevant" at the threshold
    filter and silently empty the run — the same failure mode as the single-paper
    collection.
    """
    scores = fuse([5.0, 5.0, 5.0], [0.4, 0.4, 0.4], strategy="rank_geometric")

    assert list(scores) == [10.0, 10.0, 10.0]


def test_constant_signals_tie_at_the_top_not_the_bottom():
    """With nothing to rank, papers tie at 10 — not 0.

    Normalising a constant yields zero, and a zero reads as "irrelevant" at the
    threshold filter, which would silently empty the run. This is the same
    failure mode as the old early-return on fewer than two papers.
    """
    scores = fuse([5.0, 5.0, 5.0], [0.4, 0.4, 0.4])

    assert list(scores) == [10.0, 10.0, 10.0]


def test_signals_that_cancel_are_scored_as_what_they_are():
    """A flat *fused* value is not the same as flat *inputs*.

    One paper is strong on keywords and weak on embeddings, the other the
    reverse. They are not equal — they are opposite, and the fused value says so:
    0.5 each, which is the middle of the scale. Reading the collapse as "nothing
    to rank" scored both at 10.0 and approved the whole corpus at the threshold.
    """
    scores = fuse([0.0, 10.0], [10.0, 0.0], weights={"keyword": 1.0, "embedding": 1.0})

    assert list(scores) == pytest.approx([5.0, 5.0])


def test_a_negative_weight_cannot_push_a_score_out_of_range():
    """A weight is a proportion, and the zero-sum guard did not catch a negative.

    A keyword weight of -1 against an embedding weight of 2 sums to +1, so the
    fallback for a degenerate config never fired, the negative sign survived
    normalisation, and the two extremes of the collection came out at -10 and
    +20 — outside the [0, 10] this function promises, and outside the range of
    any threshold compared against it.
    """
    scores = fuse([10.0, 0.0], [0.0, 10.0], weights={"keyword": -1.0, "embedding": 2.0})

    assert min(scores) >= 0.0
    assert max(scores) <= 10.0


def test_a_negative_weight_is_read_as_zero():
    """Zero is what the weight means: that signal does not contribute."""
    scores = fuse([10.0, 0.0], [0.0, 10.0], weights={"keyword": -1.0, "embedding": 2.0})

    assert list(scores) == pytest.approx([0.0, 10.0])


def test_all_weights_negative_fall_back_instead_of_scoring_nothing():
    scores = fuse([1.0, 2.0], [0.0, 0.0], weights={"keyword": -1.0, "embedding": -1.0})

    assert scores[1] > scores[0]


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


def test_a_flat_signal_contributes_nothing_to_the_score():
    """Flat means no ordering — and no points either.

    Asserted on the values, not the order. Giving a constant signal a full
    normalised score of 1.0 instead of 0.0 shifts every paper by the same
    constant, so the ranking is untouched and papers cross the threshold.
    """
    scores = fuse([5.0, 5.0, 5.0], [0.0, 10.0, 5.0])

    assert list(scores) == pytest.approx([0.0, 3.0, 1.5])


def test_a_zero_weight_is_not_evidence():
    """Weighting a signal at zero means it cannot be the evidence.

    A `>= 0` reads a zero weight as present, so a keyword match with no
    embedding behind it stops being "nothing matched" and becomes 10.0 for every
    paper — approving the whole corpus at the threshold, which is the failure
    this guard exists to prevent.
    """
    scores = fuse([1.0, 2.0], [0.0, 0.0], weights={"keyword": 0, "embedding": 1.0})

    assert list(scores) == [0.0, 0.0]


def test_a_flat_but_nonzero_signal_is_evidence_when_it_carries_weight():
    """A constant non-zero signal is evidence, just not an ordering.

    The keyword is weighted out, so the first half of the guard is false and the
    embedding has to carry the answer: `beta > 0`, not `beta > 1`.
    """
    scores = fuse([0.0, 0.0], [5.0, 5.0], weights={"keyword": 0.0, "embedding": 0.3})

    assert list(scores) == [10.0, 10.0]


def test_single_paper_takes_the_top_of_the_scale():
    scores = fuse([3.0], [0.2])

    assert scores == [10.0]


def test_empty_input_returns_empty():
    assert fuse([], []) == []


def test_misaligned_inputs_raise():
    """Silently zipping mismatched signals would drop papers."""
    with pytest.raises(ValueError, match="must align"):
        fuse([1.0, 2.0], [0.5])


def test_percentile_ranks_span_zero_to_one():
    ranks = percentile_ranks([30.0, 10.0, 20.0])

    assert ranks == [1.0, 0.0, 0.5]


def test_percentile_ranks_of_single_value_is_top():
    """No distribution to rank against, so the value is trivially the top."""
    assert percentile_ranks([7.0]) == [1.0]


def test_percentile_ranks_of_two_values_separates_them():
    """Two papers are a distribution; the lower one is not also at the top.

    Only reachable through `rank_geometric`, which is kept so earlier runs stay
    reproducible — a rule that quietly ties at n=2 stops reproducing them.
    """
    assert percentile_ranks([5.0, 9.0]) == [0.0, 1.0]
    assert percentile_ranks([9.0, 5.0]) == [1.0, 0.0]


def test_percentile_ranks_of_empty_list():
    assert percentile_ranks([]) == []


def fuse_with_citations(kw, sem, cit, weights=None):
    return fuse_scores(kw, sem, weights=weights, cit_scores=cit)


def test_the_citation_signal_does_not_move_the_ranking_at_the_default_weight():
    """The acceptance condition of the whole citation lot, stated as a test.

    Passing the counts is not the decision to use them: the weight is, and it
    defaults to zero so that every run written before citations existed keeps
    its ordering, paper by paper.
    """
    kw = [10.0, 1.0, 5.0]
    sem = [0.9, 0.1, 0.4]
    cit = [0.0, 1.88, 3.01]

    assert fuse_with_citations(kw, sem, cit) == fuse(kw, sem)


def test_a_configured_citation_weight_moves_the_ranking():
    kw = [10.0, 1.0]
    sem = [0.5, 0.5]
    cit = [0.0, 3.0]

    plain = fuse_with_citations(kw, sem, cit)
    weighted = fuse_with_citations(kw, sem, cit, weights={"keyword": 0.0, "embedding": 0.0, "citation": 1.0})

    assert plain[0] > plain[1]
    assert weighted[1] > weighted[0]


def test_passing_the_counts_without_the_weight_changes_nothing_either():
    """The weight is read from the merged defaults, so an explicit zero is the same as no weight."""
    kw, sem, cit = [3.0, 1.0], [0.2, 0.8], [5.0, 0.0]

    assert fuse_with_citations(kw, sem, cit, weights={"keyword": 0.7}) == fuse(kw, sem)


def test_a_corpus_at_zero_citations_is_not_evidence_of_anything():
    """Every count zero means the signal does not vary, so the pair decides as it always did.

    This is the case that would otherwise read a corpus-wide absence of data as a
    reason to move the ranking. It cannot: the zero list is the same instruction
    as no list, whatever weight is configured for it.
    """
    for kw, sem in ([[1.0, 1.0], [0.5, 0.5]], [[5.0, 1.0], [0.2, 0.8]]):
        without = fuse_with_citations(kw, sem, [0.0, 0.0])
        assert fuse_with_citations(kw, sem, [0.0, 0.0], weights={"citation": 1.0}) == without
        assert fuse_with_citations(kw, sem, [0.0, 0.0], weights={"citation": 10.0}) == without


def test_a_misaligned_citation_list_is_rejected_rather_than_zipped_short():
    with pytest.raises(ValueError):
        fuse_scores([1.0, 2.0], [1.0, 2.0], cit_scores=[1.0])


def test_the_effective_weights_are_the_defaults_when_nothing_is_configured():
    assert resolve_weights() == {"keyword": 0.7, "embedding": 0.3, "citation": 0.0}


def test_the_effective_weights_are_the_ones_configured():
    weights = {"keyword": 1.0, "embedding": 0.0}

    assert resolve_weights(weights) == {"keyword": 1.0, "embedding": 0.0, "citation": 0.0}


def test_a_negative_weight_is_reported_as_the_zero_it_is_read_as():
    """The recorded weight has to be the one applied, not the one written down."""
    assert resolve_weights({"keyword": -1.0, "embedding": 0.3})["keyword"] == 0.0


def test_a_citation_weight_on_counts_that_do_not_vary_is_reported_as_zero():
    """The corpus has no citation signal, so the weight buys nothing."""
    weights = {"keyword": 0.5, "embedding": 0.5, "citation": 1.0}

    assert resolve_weights(weights, [0.0, 0.0])["citation"] == 0.0
    assert resolve_weights(weights, None)["citation"] == 0.0
    assert resolve_weights(weights, [1.0, 2.0])["citation"] == 1.0


def test_an_all_zero_weight_set_is_reported_as_the_keyword_fallback():
    assert resolve_weights({"keyword": 0.0, "embedding": 0.0}) == {
        "keyword": 1.0, "embedding": 0.0, "citation": 0.0,
    }


@pytest.mark.parametrize(
    "weights,cit",
    [
        (None, None),
        ({"keyword": 0.0, "embedding": 0.0}, None),
        ({"keyword": -1.0, "embedding": 0.3}, [0.0, 0.0]),
        ({"keyword": 0.5, "embedding": 0.5, "citation": 1.0}, [1.0, 2.0]),
    ],
)
def test_the_fusion_applies_the_weights_that_are_reported(weights, cit):
    """The report and the arithmetic read the same rule, so they cannot disagree."""
    kw, sem = [1.0, 4.0], [4.0, 1.0]
    effective = resolve_weights(weights, cit)
    total = sum(effective.values())
    cit_norm = _minmax(cit) if cit and effective["citation"] > 0 else [0.0, 0.0]
    expected = [
        (effective["keyword"] * a + effective["embedding"] * b + effective["citation"] * c) / total
        for a, b, c in zip([0.0, 1.0], [1.0, 0.0], cit_norm)
    ]

    assert fuse_scores(kw, sem, weights=weights, cit_scores=cit) == pytest.approx(
        [value * 10.0 for value in expected]
    )
