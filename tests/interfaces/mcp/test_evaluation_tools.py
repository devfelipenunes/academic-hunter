"""Tests for the evaluation tools — the threshold and the fusion weights.

Both are the only ways to choose a number with measurements behind it instead of
by taste, so neither may answer confidently when it cannot: without a judged
collection each names the ones there are instead of picking one, and without a
run each says which artifact is missing rather than measuring nothing.
"""

import json
from unittest.mock import patch

import pytest

from academic_hunter.interfaces.mcp.tools.evaluation import (
    calibrate_inclusion_threshold,
    compare_fusion_weights,
)

DISTRIBUTION = {
    "run": "20261006_131059",
    "inclusion_predicate": "_kw_score >= 5",
    "inclusion_key": "_kw_score",
    "min_inclusion_score": 5.0,
    "counts": {"evaluated": 5, "included": 4, "excluded": 1},
    "papers": [
        {"slug": "a", "title": "Alpha", "doi": "10.1/a", "_kw_score": 30.0},
        {"slug": "b", "title": "Beta", "doi": "10.1/b", "_kw_score": 20.0},
        {"slug": "c", "title": "Gamma", "doi": "10.1/c", "_kw_score": 10.0},
        {"slug": "d", "title": "Delta", "doi": "10.1/d", "_kw_score": 5.0},
        {"slug": "e", "title": "Epsilon", "doi": "10.1/e", "_kw_score": 1.0},
    ],
}

QRELS = {
    "description": "A pilot",
    "queries": {
        "q1": {
            "text": "a topic",
            "judgments": {
                "doi:10.1/a": 2,
                "doi:10.1/b": 1,
                "doi:10.1/c": 0,
                "doi:10.1/d": 1,
                "doi:10.1/e": 0,
            },
        }
    },
}


@pytest.fixture
def project(tmp_path):
    """A project root with one run's distribution and one judged collection."""
    run_dir = tmp_path / "results" / "run_20261006_131059"
    run_dir.mkdir(parents=True)
    (run_dir / "score_distribution_20261006_131059.json").write_text(
        json.dumps(DISTRIBUTION)
    )
    (tmp_path / "evaluation").mkdir()
    (tmp_path / "evaluation" / "qrels_pilot.json").write_text(json.dumps(QRELS))
    return tmp_path


def _root(project):
    return patch(
        "academic_hunter.interfaces.mcp.tools.evaluation.get_project_root",
        return_value=project,
    )


async def test_it_sweeps_the_run_and_recommends_a_threshold(project, mock_ctx):
    with _root(project):
        result = await calibrate_inclusion_threshold(
            mock_ctx, qrels_path="evaluation/qrels_pilot.json"
        )

    assert "Threshold calibration" in result
    assert "Recommendation" in result
    assert "`_kw_score >= 5`" in result
    assert "20261006_131059" in result
    assert "run's own" in result, "the run's own threshold is not marked in the table"


async def test_the_report_says_what_the_precision_rests_on(project, mock_ctx):
    """A precision over three judgments is not a measurement, and the reply
    has to say which it is."""
    with _root(project):
        result = await calibrate_inclusion_threshold(
            mock_ctx, qrels_path="evaluation/qrels_pilot.json"
        )

    assert "of them carry a judgment" in result
    assert "Precision (floor)" in result
    assert "was judged" in result


async def test_asking_without_naming_a_collection_lists_the_ones_there_are(project, mock_ctx):
    """``evaluation/`` holds judgments for several topics, and calibrating one
    review against another's would produce a confident number that means
    nothing."""
    with _root(project):
        result = await calibrate_inclusion_threshold(mock_ctx)

    assert "qrels_path" in result
    assert "evaluation/qrels_pilot.json" in result
    assert "5 judgments" in result


async def test_a_run_with_no_distribution_is_named_as_the_missing_piece(project, mock_ctx):
    for path in (project / "results").rglob("score_distribution_*.json"):
        path.unlink()

    with _root(project):
        result = await calibrate_inclusion_threshold(
            mock_ctx, qrels_path="evaluation/qrels_pilot.json"
        )

    assert "score_distribution_" in result
    assert "run a search first" in result


async def test_a_judged_collection_that_cannot_be_read_says_so(project, mock_ctx):
    (project / "evaluation" / "broken.json").write_text('{"queries": {"q1": {"judgments": {"d": "high"}}}}')

    with _root(project):
        result = await calibrate_inclusion_threshold(
            mock_ctx, qrels_path="evaluation/broken.json"
        )

    assert "could not be read" in result
    assert "grade must be an integer" in result


async def test_a_path_that_does_not_exist_is_reported_not_swept(project, mock_ctx):
    with _root(project):
        result = await calibrate_inclusion_threshold(mock_ctx, qrels_path="evaluation/nope.json")

    assert "could not be read" in result


async def test_naming_a_run_picks_that_run(project, mock_ctx):
    other = project / "results" / "run_20260101_000000"
    other.mkdir(parents=True)
    (other / "score_distribution_20260101_000000.json").write_text(
        json.dumps({**DISTRIBUTION, "run": "20260101_000000", "min_inclusion_score": 9.0})
    )

    with _root(project):
        result = await calibrate_inclusion_threshold(
            mock_ctx, qrels_path="evaluation/qrels_pilot.json", run="20260101_000000"
        )

    assert "20260101_000000" in result
    assert "20261006_131059" not in result


async def test_a_target_precision_is_honoured(project, mock_ctx):
    with _root(project):
        result = await calibrate_inclusion_threshold(
            mock_ctx, qrels_path="evaluation/qrels_pilot.json", target_precision=0.99
        )

    assert "reaching a precision of 0.99" in result


async def test_no_judged_paper_in_the_run_says_calibration_is_impossible(project, mock_ctx):
    unrelated = {
        "queries": {"q9": {"text": "another topic", "judgments": {"doi:10.9/zzz": 2}}}
    }
    (project / "evaluation" / "other.json").write_text(json.dumps(unrelated))

    with _root(project):
        result = await calibrate_inclusion_threshold(
            mock_ctx, qrels_path="evaluation/other.json"
        )

    assert "No threshold can be recommended" in result
    assert "Judging a sample" in result


FUSION_DISTRIBUTION = {
    "run": "20261006_131059",
    "min_inclusion_score": 5.0,
    "fusion": {
        "strategy": "weighted_norm",
        "weights": {"keyword": 1.0, "embedding": 0.0, "citation": 0.0},
        "discarded": ["_sem_score"],
    },
    "counts": {"evaluated": 5},
    "papers": [
        {
            "slug": "a",
            "title": "Alpha",
            "doi": "10.1/a",
            "citations": 400,
            "_bm25_score": 30.0,
            "_kw_score": 4.0,
            "_sem_score": 0.1,
            "_citation_score": 2.6021,
            "Relevance_Score": 10.0,
        },
        {
            "slug": "b",
            "title": "Beta",
            "doi": "10.1/b",
            "citations": 90,
            "_bm25_score": 24.0,
            "_kw_score": 3.0,
            "_sem_score": 0.9,
            "_citation_score": 1.959,
            "Relevance_Score": 7.7,
        },
        {
            "slug": "c",
            "title": "Gamma",
            "doi": "10.1/c",
            "citations": 12,
            "_bm25_score": 18.0,
            "_kw_score": 2.0,
            "_sem_score": 0.5,
            "_citation_score": 1.1139,
            "Relevance_Score": 5.5,
        },
        {
            "slug": "d",
            "title": "Delta",
            "doi": "10.1/d",
            "citations": 3,
            "_bm25_score": 9.0,
            "_kw_score": 1.0,
            "_sem_score": 0.2,
            "_citation_score": 0.602,
            "Relevance_Score": 2.2,
        },
        {
            "slug": "e",
            "title": "Epsilon",
            "doi": "10.1/e",
            "citations": 0,
            "_bm25_score": 1.0,
            "_kw_score": 0.5,
            "_sem_score": 0.7,
            "_citation_score": 0.0,
            "Relevance_Score": 0.0,
        },
    ],
}

FUSION_QRELS = {
    "description": "A pilot",
    "queries": {
        "q1": {
            "text": "a topic",
            "topic": "ledgers",
            "pool": [f"doi:10.1/{letter}" for letter in "abcde"],
            "judgments": {
                "doi:10.1/a": 2,
                "doi:10.1/b": 1,
                "doi:10.1/c": 0,
                "doi:10.1/d": 1,
                "doi:10.1/e": 0,
            },
        }
    },
}


@pytest.fixture
def fusion_project(tmp_path):
    """A project root whose run recorded all three signals."""
    run_dir = tmp_path / "results" / "run_20261006_131059"
    run_dir.mkdir(parents=True)
    (run_dir / "score_distribution_20261006_131059.json").write_text(
        json.dumps(FUSION_DISTRIBUTION)
    )
    (tmp_path / "evaluation").mkdir()
    (tmp_path / "evaluation" / "qrels_pilot.json").write_text(json.dumps(FUSION_QRELS))
    return tmp_path


async def test_it_measures_every_rule_against_the_judgments(fusion_project, mock_ctx):
    with _root(fusion_project):
        result = await compare_fusion_weights(
            mock_ctx, qrels_path="evaluation/qrels_pilot.json"
        )

    assert "Fusion comparison" in result
    assert "nDCG@5" in result and "MRR" in result and "AP" in result
    for label in ("run's own (Relevance_Score)", "weighted_norm_70_30", "citations_baseline"):
        assert f"`{label}`" in result, f"{label} is missing from the table"


async def test_it_says_which_signal_each_row_read_and_which_the_run_used(
    fusion_project, mock_ctx
):
    """A run ordered by a query is not comparable to one that was not, and the
    reader cannot tell them apart from the numbers."""
    with _root(fusion_project):
        result = await compare_fusion_weights(
            mock_ctx, qrels_path="evaluation/qrels_pilot.json"
        )

    assert "`_bm25_score`" in result
    assert "the sparse side is BM25" in result
    assert "weighted_norm" in result
    assert "`_sem_score`" in result, "the run's own discarded signal is not named"


async def test_it_does_not_pass_off_the_deleted_script_s_rules_as_measured(
    fusion_project, mock_ctx
):
    with _root(fusion_project):
        result = await compare_fusion_weights(
            mock_ctx, qrels_path="evaluation/qrels_pilot.json"
        )

    assert "Not reproducible from this repository" in result
    for name in ("max_rank", "rrf_60", "arith_rank", "min_rank"):
        assert f"- `{name}` — " in result


async def test_the_fusion_tool_lists_the_collections_it_could_measure_against(
    fusion_project, mock_ctx
):
    with _root(fusion_project):
        result = await compare_fusion_weights(mock_ctx)

    assert "qrels_path" in result
    assert "evaluation/qrels_pilot.json" in result


async def test_the_fusion_tool_names_the_missing_distribution(
    fusion_project, mock_ctx
):
    for path in (fusion_project / "results").rglob("score_distribution_*.json"):
        path.unlink()

    with _root(fusion_project):
        result = await compare_fusion_weights(
            mock_ctx, qrels_path="evaluation/qrels_pilot.json"
        )

    assert "score_distribution_" in result
    assert "run a search first" in result


async def test_a_collection_that_cannot_be_read_says_so(fusion_project, mock_ctx):
    (fusion_project / "evaluation" / "broken.json").write_text(
        '{"queries": {"q1": {"judgments": {"d": "high"}}}}'
    )

    with _root(fusion_project):
        result = await compare_fusion_weights(mock_ctx, qrels_path="evaluation/broken.json")

    assert "could not be read" in result


async def test_a_collection_that_judges_nothing_this_run_scored_says_so(
    fusion_project, mock_ctx
):
    """Empty is the honest answer, and the alternative is a table of zeros that
    reads as a measurement."""
    (fusion_project / "evaluation" / "other.json").write_text(
        json.dumps(
            {
                "queries": {
                    "q9": {
                        "text": "another topic",
                        "pool": ["doi:10.9/zzz"],
                        "judgments": {"doi:10.9/zzz": 2},
                    }
                }
            }
        )
    )

    with _root(fusion_project):
        result = await compare_fusion_weights(mock_ctx, qrels_path="evaluation/other.json")

    assert "No judgments to measure against" in result
    assert "| Rule |" not in result


async def test_the_fusion_tool_picks_the_named_run(fusion_project, mock_ctx):
    other = fusion_project / "results" / "run_20260101_000000"
    other.mkdir(parents=True)
    (other / "score_distribution_20260101_000000.json").write_text(
        json.dumps({**FUSION_DISTRIBUTION, "run": "20260101_000000"})
    )

    with _root(fusion_project):
        result = await compare_fusion_weights(
            mock_ctx, qrels_path="evaluation/qrels_pilot.json", run="20260101_000000"
        )

    assert "20260101_000000" in result
    assert "20261006_131059" not in result
