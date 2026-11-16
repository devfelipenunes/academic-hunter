"""The retrieval measurement, over data that ships with the repository.

Two things are asserted here, and the second is the one that matters. The first
is that both modes still run over the versioned fixtures: the pool carries its
own candidates and judgments, and the qrels' 25 targets resolve against the run
beside it. The second is that the harness cannot print a number that reads like
a measurement when a leg did not run or the corpus is not the one the qrels
describes — which is the failure the project exists to prevent, and the one
place it would be least visible.
"""

import json
from argparse import Namespace
from pathlib import Path

import harness
import pytest

EVALUATION = Path(__file__).resolve().parent
POOL = EVALUATION / "pool_blockchain_governance.json"
QRELS = EVALUATION / "qrels_blockchain.json"
RUN = EVALUATION / "fixtures" / "run_20261013_093241"


def args(**overrides) -> Namespace:
    base = {
        "weights": None,
        "dense": "none",
        "rerank": False,
        "top_n": 20,
        "rerank_model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
    }
    return Namespace(**{**base, **overrides})


def test_the_pool_carries_everything_its_measurement_needs():
    """No run, no network, no model: this is what a fresh clone can still do."""
    result = harness.evaluate_pool(POOL, args())

    assert result["queries"] == 5
    assert result["candidates"] == 50
    assert result["ndcg@10"] > 0.0


def test_the_qrels_targets_all_resolve_against_the_versioned_run():
    """`answered` is the count this asserts on: a zero here is not a bad score.

    It is the harness saying the corpus it was handed is not the one the qrels
    describes, and every metric below it is then about nothing.
    """
    result = harness.evaluate(RUN, json.loads(QRELS.read_text()), args())

    assert result["questions"] == 25
    assert result["answered"] == 25


def test_a_run_with_no_dataset_says_which_directory_it_looked_in(tmp_path):
    with pytest.raises(FileNotFoundError) as exc:
        harness.load_papers(tmp_path)

    assert str(tmp_path) in str(exc.value)
    assert "academic_dataset_*.csv" in str(exc.value)


def test_the_pool_records_the_judged_run_the_qrels_names():
    """Two fixtures, two measurements, and they are not of the same corpus."""
    qrels = json.loads(QRELS.read_text())
    pool = json.loads(POOL.read_text())

    assert qrels["run"] == RUN.name
    assert pool["provenance"]["original_provenance"]["source_csv"] != qrels["run"]


def test_a_dense_leg_that_cannot_run_is_not_reported_as_having_run(monkeypatch):
    monkeypatch.setattr(harness, "query_dense_scores", lambda texts, query: None)

    result = harness.evaluate_pool(POOL, args(dense="query"))

    assert result["dense_requested"] is True
    assert result["dense_ran"] is False
    assert "REQUESTED BUT DID NOT RUN" in harness.legs_line(result)


def test_a_dense_leg_that_runs_is_reported_as_having_run(monkeypatch):
    monkeypatch.setattr(
        harness, "query_dense_scores", lambda texts, query: [0.5 for _ in texts]
    )

    result = harness.evaluate_pool(POOL, args(dense="query"))

    assert result["dense_ran"] is True
    assert "dense=ran" in harness.legs_line(result)


def test_a_rerank_that_was_skipped_is_not_reported_as_having_run(monkeypatch):
    """`rerank_texts` returns ``None`` without `sentence_transformers`, by design."""
    monkeypatch.setattr(
        harness, "rerank_texts", lambda question, texts, model_name=None: None
    )

    result = harness.evaluate_pool(POOL, args(rerank=True))

    assert result["rerank_requested"] is True
    assert result["rerank_ran"] is False
    assert "REQUESTED BUT DID NOT RUN" in harness.legs_line(result)


def test_a_leg_nobody_asked_for_is_reported_as_off():
    line = harness.legs_line(harness.evaluate_pool(POOL, args()))

    assert "dense=off" in line
    assert "rerank=off" in line
