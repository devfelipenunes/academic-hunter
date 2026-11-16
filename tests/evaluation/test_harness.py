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
MICROPLASTICS_DATASET = EVALUATION.parent.parent / "research" / "microplastics-freshwater" / "consolidated-adjudication-round3.csv"
MICROPLASTICS_QRELS = EVALUATION / "qrels_microplastics_known_item_seed.json"
MICROPLASTICS_REVIEW = EVALUATION / "qrels_microplastics_known_item_review.csv"
MICROPLASTICS_POOL = EVALUATION / "microplastics_relevance_pool_seed.json"
MICROPLASTICS_POOL_REVIEW = EVALUATION / "microplastics_relevance_pool_review.csv"


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


def test_a_direct_csv_can_be_evaluated_as_a_corpus():
    qrels = json.loads(MICROPLASTICS_QRELS.read_text())

    assert qrels["task"] == "known_item_retrieval"
    assert "not gold labels" in qrels["annotation_status"]
    assert len(harness.load_papers(MICROPLASTICS_DATASET)) == 149

    result = harness.evaluate(MICROPLASTICS_DATASET, qrels, args())

    assert result["questions"] == 10
    assert result["answered"] == 10
    assert 0.0 <= result["recall@10"] <= 1.0


def test_microplastics_seed_has_a_human_validation_worksheet():
    import csv

    with MICROPLASTICS_REVIEW.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    assert len(rows) == 10
    assert all(row["Query_Clear"] == "" and row["Target_Correct"] == "" for row in rows)


def test_microplastics_relevance_pool_is_labeled_provisional_and_reviewable():
    import csv

    pool = json.loads(MICROPLASTICS_POOL.read_text())
    assert pool["provenance"]["annotation_status"] == "ai_provisional_pending_human_validation"
    assert len(pool["queries"]) == 5
    assert all(len(query["pool"]) == 12 for query in pool["queries"].values())
    assert all(query["judgment_status"] == "ai_provisional_pending_human_validation"
               for query in pool["queries"].values())

    result = harness.evaluate_pool(MICROPLASTICS_POOL, args())
    assert result["queries"] == 5
    assert result["candidates"] == 12
    assert result["annotation_status"] == "ai_provisional_pending_human_validation"
    assert 0.0 <= result["ndcg@10"] <= 1.0

    with MICROPLASTICS_POOL_REVIEW.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 60
    assert all(row["Human_Grade"] == "" for row in rows)


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


def test_dense_evaluation_embeds_the_corpus_once_per_process(monkeypatch):
    calls = []

    def embed(texts):
        calls.append(list(texts))
        return [[1.0, 0.0] if "target" in text else [0.0, 1.0] for text in texts]

    monkeypatch.setattr(harness, "_embedder", lambda: embed)
    harness._embedded_corpus.cache_clear()
    try:
        first = harness.query_dense_scores(["target paper", "other paper"], "target question")
        second = harness.query_dense_scores(["target paper", "other paper"], "other question")
    finally:
        harness._embedded_corpus.cache_clear()

    assert first == [1.0, 0.0]
    assert second == [0.0, 1.0]
    assert [len(batch) for batch in calls] == [2, 1, 1]
