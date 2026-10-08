"""The threshold is chosen from measurements, so the measurements must be right.

Every number here is checked against a collection small enough to count by hand:
five papers, three of them judged relevant, one score each. A calibration that
reads well and computes the wrong precision is worse than no calibration, since
its whole purpose is to be the evidence for a setting.
"""

import pytest

from academic_hunter.core.evaluation import (
    Calibration,
    Sweep,
    candidate_thresholds,
    sweep_threshold,
)
from academic_hunter.core.evaluation.qrels import Judgment, Qrels


def paper(doi: str, value: float, title: str = "") -> dict:
    return {"title": title or doi, "doi": doi, "_kw_score": value}


PAPERS = [
    paper("10.1/a", 30.0),
    paper("10.1/b", 20.0),
    paper("10.1/c", 10.0),
    paper("10.1/d", 5.0),
    paper("10.1/e", 1.0),
]


def qrels_with(grades: dict) -> Qrels:
    return Qrels(queries={"q1": Judgment(query_id="q1", text="topic", grades=grades)})


THREE_OF_FIVE = qrels_with(
    {"doi:10.1/a": 2, "doi:10.1/b": 1, "doi:10.1/c": 0, "doi:10.1/d": 1, "doi:10.1/e": 0}
)


def test_candidates_are_the_papers_own_scores():
    """The metrics only move where a paper crosses, so a grid would be noise."""
    assert candidate_thresholds([30.0, 10.0, 20.0]) == [0.0, 10.0, 20.0, 30.0]


def test_including_everything_is_always_a_candidate():
    """``0`` is the position "trust the screening and keep it all"."""
    assert candidate_thresholds([]) == [0.0]
    assert candidate_thresholds([0.0]) == [0.0]


def test_thinning_keeps_the_range_and_the_limit():
    values = [float(v) for v in range(1, 101)]
    thinned = candidate_thresholds(values, limit=10)

    assert len(thinned) == 10
    assert thinned[0] == 0.0
    assert thinned[-1] == 100.0, "thinning from the head would hide the top of the range"
    assert all(b > a for a, b in zip(thinned, thinned[1:]))


def test_a_threshold_admits_the_papers_at_or_above_it():
    calibration = sweep_threshold(PAPERS, THREE_OF_FIVE, thresholds=[0.0, 10.0, 25.0])
    by_threshold = {row.threshold: row for row in calibration.rows}

    assert by_threshold[0.0].included == 5
    assert by_threshold[10.0].included == 3
    assert by_threshold[25.0].included == 1


def test_precision_counts_only_the_judged_papers_it_admits():
    calibration = sweep_threshold(PAPERS, THREE_OF_FIVE, thresholds=[0.0])
    row = calibration.rows[0]

    assert row.judged == 5
    assert row.relevant == 3
    assert row.precision == pytest.approx(0.6)
    assert row.recall == pytest.approx(1.0)
    assert row.coverage == pytest.approx(1.0)


def test_the_floor_is_what_precision_would_be_with_every_unjudged_paper_irrelevant():
    """Judged-relevant ``a`` and ``d`` are admitted; ``e`` is unjudged.

    The truth is somewhere in between and the tool says so rather than picking
    one end and calling it precision.
    """
    calibration = sweep_threshold(PAPERS, THREE_OF_FIVE, thresholds=[5.0])
    row = calibration.rows[0]

    assert row.included == 4
    assert row.judged == 4
    assert row.relevant == 3
    assert row.precision == pytest.approx(0.75)
    assert row.precision_floor == pytest.approx(0.75)


def test_an_unjudged_paper_widens_the_gap_between_precision_and_its_floor():
    unjudged = qrels_with({"doi:10.1/a": 2, "doi:10.1/b": 1, "doi:10.1/c": 0})
    calibration = sweep_threshold(PAPERS, unjudged, thresholds=[0.0])
    row = calibration.rows[0]

    assert row.included == 5
    assert row.judged == 3
    assert row.precision == pytest.approx(2 / 3)
    assert row.precision_floor == pytest.approx(2 / 5)


def test_recall_ignores_what_the_search_never_found():
    """A judged-relevant paper outside the run is not the threshold's doing.

    Counting it would blame the cut for the search, and the recommendation would
    chase a number no threshold can move.
    """
    partial = qrels_with(
        {
            "doi:10.1/a": 2,
            "doi:10.1/b": 1,
            "doi:10.1/never-collected": 2,
        }
    )
    calibration = sweep_threshold(PAPERS, partial, thresholds=[0.0])

    assert calibration.n_relevant == 3
    assert calibration.n_relevant_evaluated == 2
    assert calibration.missed_by_retrieval == 1
    assert calibration.rows[0].recall == pytest.approx(1.0)


def test_recall_falls_as_the_threshold_rises_past_a_relevant_paper():
    calibration = sweep_threshold(PAPERS, THREE_OF_FIVE, thresholds=[0.0, 15.0])
    low, high = calibration.rows

    assert low.recall == pytest.approx(1.0)
    assert high.recall == pytest.approx(2 / 3)


def test_f1_is_the_harmonic_mean_of_the_two():
    calibration = sweep_threshold(PAPERS, THREE_OF_FIVE, thresholds=[15.0])
    row = calibration.rows[0]

    expected = 2 * row.precision * row.recall / (row.precision + row.recall)
    assert row.f1 == pytest.approx(expected)


def test_two_records_of_one_study_are_one_paper():
    """The same study from two databases shares its DOI, and one judgment.

    Kept at the higher of the two scores: the study is in the review when its
    better copy qualifies, and counting both would double its weight.
    """
    duplicate = [paper("10.1/a", 2.0), paper("10.1/a", 30.0), paper("10.1/b", 1.0)]
    calibration = sweep_threshold(duplicate, THREE_OF_FIVE, thresholds=[0.0])

    assert calibration.evaluated == 2
    assert calibration.rows[0].included == 2

    at_thirty = sweep_threshold(duplicate, THREE_OF_FIVE, thresholds=[30.0])
    assert at_thirty.rows[0].included == 1


def test_a_paper_with_no_doi_is_identified_by_its_title():
    without_doi = [{"title": "Latency in Ledgers", "doi": "", "_kw_score": 4.0}]
    judged = qrels_with({"title:latencyinledgers": 2})
    calibration = sweep_threshold(without_doi, judged, thresholds=[0.0])

    assert calibration.judged == 1
    assert calibration.rows[0].relevant == 1


def test_the_recommendation_is_the_lowest_threshold_that_meets_the_target():
    """Recall is what a review cannot recover later, so precision is the floor
    and everything above it is kept."""
    calibration = sweep_threshold(PAPERS, THREE_OF_FIVE, thresholds=[0.0, 10.0, 25.0])
    recommended = calibration.recommend(target_precision=0.9)

    assert recommended is not None
    assert recommended.threshold == 25.0


def test_a_target_nothing_reaches_recommends_nothing():
    calibration = sweep_threshold(PAPERS, THREE_OF_FIVE, thresholds=[0.0])
    assert calibration.recommend(target_precision=1.0) is None


def test_without_a_target_the_best_f1_wins():
    calibration = sweep_threshold(PAPERS, THREE_OF_FIVE, thresholds=[0.0, 10.0, 25.0])
    recommended = calibration.recommend()

    assert recommended is not None
    assert recommended.f1 == max(row.f1 for row in calibration.rows)


def test_a_sample_of_nothing_is_never_recommended():
    """A threshold whose included set was never judged has no precision to
    offer, and F1 cannot distinguish it from a measured disaster."""
    calibration = sweep_threshold(PAPERS, qrels_with({"doi:10.9/other": 2}))
    assert calibration.recommend() is None


def test_a_missing_signal_counts_as_zero_rather_than_raising():
    papers = [{"title": "No score", "doi": "10.1/x"}]
    calibration = sweep_threshold(papers, THREE_OF_FIVE, thresholds=[0.0, 1.0])

    assert calibration.evaluated == 1
    assert calibration.rows[0].included == 1
    assert calibration.rows[1].included == 0


def test_the_row_for_a_threshold_is_the_nearest_reported_one():
    calibration = sweep_threshold(PAPERS, THREE_OF_FIVE, thresholds=[0.0, 10.0, 20.0])
    assert calibration.row_for(9.5).threshold == 10.0
    assert calibration.row_for(1000.0).threshold == 20.0


def test_the_report_is_serialisable():
    calibration = sweep_threshold(PAPERS, THREE_OF_FIVE, thresholds=[0.0])
    payload = calibration.as_dict()

    assert payload["key"] == "_kw_score"
    assert payload["rows"][0]["precision"] == pytest.approx(0.6)


def test_the_dataclasses_are_the_ones_the_package_exports():
    assert Calibration.__module__.endswith("calibration")
    assert Sweep.__module__.endswith("calibration")
