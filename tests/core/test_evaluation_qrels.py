"""Tests for the judged-collection format and the evaluation runner."""

import json

import pytest

from academic_hunter.core.evaluation import (
    Judgment,
    Qrels,
    QrelsError,
    evaluate_run,
    load_qrels,
)
from academic_hunter.core.evaluation.qrels import documents_for, doc_id_for, save_qrels, topics
from academic_hunter.core.evaluation.runner import (
    build_rankings,
    build_rankings_timed,
    unjudged_in_pool,
)

VALID = {
    "description": "pilot",
    "queries": {
        "q1": {"text": "term weighting", "judgments": {"d1": 2, "d2": 1, "d3": 0}},
        "q2": {"text": "cross-encoder", "judgments": {"d2": 3, "d4": 1}},
    },
}


def _write(tmp_path, payload):
    path = tmp_path / "qrels.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ── doc ids ─────────────────────────────────────────────────────────────────


def test_doc_id_prefers_doi():
    assert doc_id_for("Some Title", "10.1234/ABC") == "doi:10.1234/abc"


def test_doc_id_falls_back_to_normalised_title():
    assert doc_id_for("Sentence-BERT: Embeddings!") == "title:sentencebertembeddings"


def test_doc_id_normalises_case_and_punctuation():
    """Two spellings of the same title must produce the same id."""
    assert doc_id_for("A  Study, of Things!") == doc_id_for("a study of things")


def test_doc_id_of_blank_is_empty_title():
    assert doc_id_for("") == "title:"


# ── loading ─────────────────────────────────────────────────────────────────


def test_load_valid_qrels(tmp_path):
    qrels = load_qrels(_write(tmp_path, VALID))

    assert len(qrels) == 2
    assert qrels.description == "pilot"
    assert qrels.n_judgments == 5
    assert qrels.n_relevant == 4  # d3 is grade 0
    assert qrels["q1"].relevant_ids == ["d1", "d2"]


def test_missing_file_raises(tmp_path):
    with pytest.raises(QrelsError, match="not found"):
        load_qrels(tmp_path / "nope.json")


def test_invalid_json_raises(tmp_path):
    path = tmp_path / "qrels.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(QrelsError, match="not valid JSON"):
        load_qrels(path)


def test_empty_queries_raises(tmp_path):
    with pytest.raises(QrelsError, match="non-empty"):
        load_qrels(_write(tmp_path, {"queries": {}}))


def test_string_grade_is_rejected(tmp_path):
    """A string grade would silently become "not relevant" — reject it instead."""
    payload = {"queries": {"q1": {"text": "t", "judgments": {"d1": "2"}}}}

    with pytest.raises(QrelsError, match="must be an integer"):
        load_qrels(_write(tmp_path, payload))


def test_float_grade_is_rejected(tmp_path):
    payload = {"queries": {"q1": {"text": "t", "judgments": {"d1": 2.5}}}}

    with pytest.raises(QrelsError, match="must be an integer"):
        load_qrels(_write(tmp_path, payload))


def test_boolean_grade_is_rejected(tmp_path):
    """`True` is an int in Python; accepting it would hide a malformed file."""
    payload = {"queries": {"q1": {"text": "t", "judgments": {"d1": True}}}}

    with pytest.raises(QrelsError, match="must be an integer"):
        load_qrels(_write(tmp_path, payload))


def test_negative_grade_is_rejected(tmp_path):
    payload = {"queries": {"q1": {"text": "t", "judgments": {"d1": -1}}}}

    with pytest.raises(QrelsError, match="negative"):
        load_qrels(_write(tmp_path, payload))


def test_query_without_judgments_is_allowed(tmp_path):
    """A query whose documents are all unjudged is odd but not malformed."""
    payload = {"queries": {"q1": {"text": "t"}}}

    qrels = load_qrels(_write(tmp_path, payload))

    assert qrels["q1"].grades == {}
    assert qrels["q1"].relevant_ids == []


def test_roundtrip_preserves_grades(tmp_path):
    qrels = load_qrels(_write(tmp_path, VALID))
    out = save_qrels(qrels, tmp_path / "out.json")

    reloaded = load_qrels(out)

    assert reloaded["q1"].grades == qrels["q1"].grades
    assert reloaded["q2"].text == qrels["q2"].text


def test_stats_summarises_the_collection(tmp_path):
    stats = load_qrels(_write(tmp_path, VALID)).stats()

    assert stats["queries"] == 2
    assert stats["judgments"] == 5
    assert stats["relevant"] == 4


# ── runner ──────────────────────────────────────────────────────────────────


def _qrels():
    return Qrels(
        queries={
            "q1": Judgment("q1", "t1", {"a": 3, "b": 1}),
            "q2": Judgment("q2", "t2", {"c": 2}),
        }
    )


def test_evaluate_run_reports_per_query_and_mean():
    report = evaluate_run(
        _qrels(),
        {"q1": ["a", "b"], "q2": ["c"]},
        ks=[2],
    )

    assert report.n_queries == 2
    assert report.per_query["q1"]["ndcg@2"] == pytest.approx(1.0)
    assert report.mean["ndcg@2"] == pytest.approx(1.0)


def test_evaluate_run_skips_queries_without_a_ranking():
    """A query the retriever did not answer is left out, not scored as zero."""
    report = evaluate_run(_qrels(), {"q1": ["a", "b"]}, ks=[2])

    assert report.n_queries == 1
    assert "q2" not in report.per_query


def test_evaluate_run_measures_judged_coverage():
    """Half of the top-2 are judged, which caps how much the score means."""
    report = evaluate_run(_qrels(), {"q1": ["a", "zzz"]}, ks=[2])

    assert report.judged_coverage["q1"] == pytest.approx(0.5)


def test_min_coverage_surfaces_the_weakest_query():
    """The report's headline coverage is the worst query, not the average."""
    report = evaluate_run(
        _qrels(),
        {"q1": ["a", "b"], "q2": ["zzz"]},
        ks=[2],
    )

    assert report.min_coverage == pytest.approx(0.0)


def test_report_as_dict_is_serialisable():
    report = evaluate_run(_qrels(), {"q1": ["a"], "q2": ["c"]}, ks=[1])

    json.dumps(report.as_dict())  # must not raise


def test_build_rankings_sorts_by_score_descending():
    corpus = [{"id": "low"}, {"id": "high"}, {"id": "mid"}]
    scores = {"low": 0.1, "high": 0.9, "mid": 0.5}

    rankings = build_rankings(
        corpus,
        {"q": "text"},
        scorer=lambda doc, q: scores[doc["id"]],
        doc_id=lambda doc: doc["id"],
    )

    assert rankings["q"] == ["high", "mid", "low"]


def test_build_rankings_truncates_to_top_k():
    corpus = [{"id": str(i)} for i in range(10)]

    rankings = build_rankings(
        corpus,
        {"q": "text"},
        scorer=lambda doc, q: float(doc["id"]),
        doc_id=lambda doc: doc["id"],
        top_k=3,
    )

    assert rankings["q"] == ["9", "8", "7"]


def test_a_negative_top_k_is_rejected_rather_than_truncating():
    """`scored[:-1]` keeps four of five documents and reads as a valid ranking.

    A negative limit reached the slice as an index, so the corpus silently lost
    its last document — and every metric computed on it looked fine.
    """
    corpus = [{"id": str(i)} for i in range(5)]

    with pytest.raises(ValueError, match="top_k"):
        build_rankings(
            corpus, {"q": "text"},
            scorer=lambda doc, q: float(doc["id"]),
            doc_id=lambda doc: doc["id"],
            top_k=-1,
        )


def test_a_zero_top_k_is_an_empty_ranking_not_an_error():
    """Asking for nothing is a request that can be honoured."""
    corpus = [{"id": "a"}]

    rankings = build_rankings(
        corpus, {"q": "text"}, scorer=lambda doc, q: 1.0, doc_id=lambda doc: doc["id"], top_k=0
    )

    assert rankings == {"q": []}


def test_build_rankings_timed_rejects_a_negative_top_k_too():
    """The two entry points must not disagree about what a limit is."""
    corpus = [{"id": str(i)} for i in range(5)]

    with pytest.raises(ValueError, match="top_k"):
        build_rankings_timed(
            corpus, {"q": "text"},
            scorer=lambda doc, q: float(doc["id"]),
            doc_id=lambda doc: doc["id"],
            top_k=-1,
        )


def test_build_rankings_uses_the_same_pool_for_every_query():
    """A constant candidate set keeps the comparison about the scorer."""
    corpus = [{"id": "a"}, {"id": "b"}]

    rankings = build_rankings(
        corpus,
        {"q1": "one", "q2": "two"},
        scorer=lambda doc, q: 1.0,
        doc_id=lambda doc: doc["id"],
    )

    assert set(rankings["q1"]) == set(rankings["q2"]) == {"a", "b"}


def test_unjudged_in_pool_lists_unjudged_documents():
    qrels = _qrels()

    assert unjudged_in_pool(qrels, ["a", "c", "zzz"]) == {"zzz"}


# ── per-query pools and topics ──────────────────────────────────────────────


def test_pool_and_topic_round_trip(tmp_path):
    """Both fields survive a save/load cycle."""
    payload = {
        "queries": {
            "q1": {"text": "t", "topic": "alpha", "pool": ["d1", "d2"],
                   "judgments": {"d1": 2, "d2": 0}},
        }
    }
    qrels = load_qrels(_write(tmp_path, payload))
    reloaded = load_qrels(save_qrels(qrels, tmp_path / "out.json"))

    assert reloaded["q1"].topic == "alpha"
    assert reloaded["q1"].pool == ["d1", "d2"]


def test_absent_pool_defaults_to_empty(tmp_path):
    """Single-topic files predate pools and must keep working."""
    payload = {"queries": {"q1": {"text": "t", "judgments": {"d1": 2}}}}

    qrels = load_qrels(_write(tmp_path, payload))

    assert qrels["q1"].pool == []
    assert qrels["q1"].topic == ""


def test_blocks_the_loader_does_not_read_survive_a_round_trip(tmp_path):
    """`provenance` and `documents` are the evidence for the grades.

    A reviewer who edits grades and saves through `save_qrels` must not lose
    the record of how those grades were made, nor the documents they were made
    against — the shipped collection embeds all 108 abstracts for exactly that
    reason, and `results/` is not versioned.
    """
    payload = {
        "description": "pilot",
        "provenance": {"annotators": 1, "annotation_method": "title+abstract"},
        "documents": {"d1": {"title": "A paper", "abstract": "..."}},
        "queries": {"q1": {"text": "t", "judgments": {"d1": 2}}},
    }
    source = _write(tmp_path, payload)

    result = json.loads(save_qrels(load_qrels(source), tmp_path / "out.json").read_text())

    assert result["provenance"] == payload["provenance"]
    assert result["documents"] == payload["documents"]


def test_a_round_trip_preserves_the_key_order_of_the_original(tmp_path):
    """The file is meant to be read by a human; the shape should not shuffle."""
    payload = {
        "description": "pilot",
        "provenance": {"annotators": 1},
        "documents": {"d1": {"title": "A paper"}},
        "queries": {"q1": {"text": "t", "judgments": {"d1": 2}}},
    }
    source = _write(tmp_path, payload)

    result = json.loads(save_qrels(load_qrels(source), tmp_path / "out.json").read_text())

    assert list(result) == list(payload)


def test_saving_preserves_the_authored_query_order(tmp_path):
    """The reviewer's order survives the save.

    The file is edited by hand; sorting it on the way out would bury the
    reviewer's own edits under a reordering of every query.
    """
    payload = {
        "queries": {
            "zeta": {"text": "t", "judgments": {"d2": 1}},
            "alpha": {"text": "t2", "judgments": {"d1": 2}},
        },
    }

    saved = save_qrels(load_qrels(_write(tmp_path, payload)), tmp_path / "out.json")

    assert list(json.loads(saved.read_text())["queries"]) == ["zeta", "alpha"]


def test_saving_what_was_just_loaded_is_byte_stable(tmp_path):
    """A second save shows only real edits, never a reshuffle."""
    payload = {
        "description": "pilot",
        "provenance": {"annotators": 1},
        "queries": {
            "zeta": {"text": "t", "topic": "alpha", "pool": ["d2", "d1"],
                     "judgments": {"d2": 1, "d1": 0}},
            "alpha": {"text": "t2", "judgments": {"d1": 2}},
        },
    }

    once = save_qrels(load_qrels(_write(tmp_path, payload)), tmp_path / "1.json")
    twice = save_qrels(load_qrels(once), tmp_path / "2.json")

    assert once.read_text(encoding="utf-8") == twice.read_text(encoding="utf-8")


def test_documents_for_returns_the_declared_pool():
    qrels = Qrels(queries={
        "q1": Judgment("q1", "t", {"a": 1, "b": 1}, pool=["a", "b", "c"]),
    })

    assert documents_for(qrels, "q1") == ["a", "b", "c"]


def test_documents_for_falls_back_to_every_judged_document():
    """No pool declared means the whole judged collection, sorted for stability."""
    qrels = Qrels(queries={
        "q1": Judgment("q1", "t", {"b": 1}),
        "q2": Judgment("q2", "t", {"a": 1, "c": 0}),
    })

    assert documents_for(qrels, "q1") == ["a", "b", "c"]


def test_documents_for_unknown_query_raises():
    with pytest.raises(QrelsError, match="unknown query"):
        documents_for(_qrels(), "nope")


def test_topics_groups_queries_in_first_seen_order():
    qrels = Qrels(queries={
        "a1": Judgment("a1", "t", {}, topic="alpha"),
        "b1": Judgment("b1", "t", {}, topic="beta"),
        "a2": Judgment("a2", "t", {}, topic="alpha"),
    })

    assert topics(qrels) == {"alpha": ["a1", "a2"], "beta": ["b1"]}


def test_topics_puts_untagged_queries_under_empty_string():
    qrels = Qrels(queries={"q1": Judgment("q1", "t", {})})

    assert topics(qrels) == {"": ["q1"]}
