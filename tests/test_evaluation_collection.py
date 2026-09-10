"""Validity checks for the shipped judged collection.

The qrels is the ground truth every retrieval claim rests on, so it is checked
on every test run. The failure it guards against is silent divergence: a
judgment added for a document that is no longer in the pool (or an embedded
document that no longer matches its id) would make the metrics score against
documents the ranker can never return, and the report would just look worse
without saying why.
"""

import json
from pathlib import Path

import pytest

from academic_hunter.core.evaluation import load_qrels
from academic_hunter.core.evaluation.qrels import RELEVANT_THRESHOLD, doc_id_for

ROOT = Path(__file__).resolve().parent.parent
QRELS_PATH = ROOT / "papers" / "evaluation" / "qrels_pilot_genre_analysis.json"


@pytest.fixture(scope="module")
def payload():
    return json.loads(QRELS_PATH.read_text(encoding="utf-8"))


def test_collection_file_exists_and_loads():
    """The collection parses under its own loader."""
    qrels = load_qrels(QRELS_PATH)

    assert len(qrels) > 0
    assert qrels.n_judgments > 0


def test_collection_is_self_contained(payload):
    """Documents ship with the judgments.

    The corpus lives under a git-ignored directory, so a qrels that only
    referenced a CSV path would be unusable on a fresh clone.
    """
    assert payload.get("documents"), (
        "the qrels must embed its documents — the source corpus is not in "
        "version control"
    )


def test_every_judged_document_is_present(payload):
    """No judgment may point at a document the ranker can never return."""
    documents = set(payload["documents"])
    judged = {d for q in payload["queries"].values() for d in q["judgments"]}

    assert not (judged - documents), (
        f"judged but not embedded: {sorted(judged - documents)[:3]}"
    )


def test_embedded_ids_match_their_document_content(payload):
    """Each embedded id must be derivable from the document it names.

    Ids come from the DOI when there is one and the title otherwise, so a title
    or DOI edited without re-deriving the id would detach the judgment from the
    document it was assigned to.
    """
    mismatched = []
    for doc_id, doc in payload["documents"].items():
        derived = doc_id_for(doc.get("title", ""), doc.get("doi", ""))
        if derived != doc_id:
            mismatched.append((doc_id, derived))

    assert not mismatched, (
        f"{len(mismatched)} embedded id(s) do not match their document, e.g. {mismatched[:2]}"
    )


def test_every_query_has_relevant_documents(payload):
    """A query with no relevant document cannot be scored, only reported as 0."""
    empty = []
    for query_id, query in payload["queries"].items():
        grades = query.get("judgments", {})
        if not any(g >= RELEVANT_THRESHOLD for g in grades.values()):
            empty.append(query_id)

    assert not empty, f"queries with no relevant documents: {empty}"


def test_every_query_records_its_information_need(payload):
    """Metrics are meaningless without knowing what was being asked for."""
    missing = [
        qid for qid, q in payload["queries"].items() if not q.get("text", "").strip()
    ]

    assert not missing, f"queries without a stated information need: {missing}"


def test_grades_are_in_the_documented_range(payload):
    """Grades are 0-2: not relevant / partially / directly relevant."""
    bad = [
        (qid, doc, grade)
        for qid, q in payload["queries"].items()
        for doc, grade in q["judgments"].items()
        if not isinstance(grade, int) or grade < 0 or grade > 2
    ]

    assert not bad, f"grades outside 0-2: {bad[:3]}"


def test_provenance_is_recorded(payload):
    """A collection without provenance cannot be audited or extended."""
    provenance = payload.get("provenance", {})

    assert provenance.get("source_csv"), "source corpus not recorded"
    assert provenance.get("selection"), "pool selection rule not recorded"
    assert provenance.get("annotation_method"), "annotation method not recorded"


def test_each_pool_spans_the_score_range(payload):
    """No pool may be truncated at the top of the score being tested.

    Selecting candidates only by the score under test restricts its range
    *within that pool*, which makes the score look undiscriminating for reasons
    that have nothing to do with its quality. This is a regression guard: the
    first version of the genre pool was top-30-by-score only and produced
    exactly that artifact.

    Checked per pool, not over the union of all documents — a wide spread across
    two topics would mask a truncated pool inside one of them.
    """
    topics_seen = {}
    for qid, query in payload["queries"].items():
        topics_seen.setdefault(query.get("topic") or "(sem tópico)", set()).update(
            query["pool"]
        )

    assert topics_seen, "no pools declared"

    for topic, pool_ids in topics_seen.items():
        scores = [
            float(payload["documents"][d]["pipeline_relevance_score"])
            for d in pool_ids
            if payload["documents"][d].get("pipeline_relevance_score") not in (None, "")
        ]
        assert scores, f"{topic}: no pipeline scores recorded in the pool"

        spread = max(scores) - min(scores)
        assert spread > 5.0, (
            f"{topic}: pool score range is only {spread:.1f} — it looks truncated, "
            "which biases the comparison against the score being evaluated"
        )


def test_every_query_declares_a_pool(payload):
    """A query without a pool would be ranked over every judged document.

    With two topics in one file, that would score a blockchain query against the
    genre documents and vice versa — unjudged for it, and counted as irrelevant.
    """
    missing = [qid for qid, q in payload["queries"].items() if not q.get("pool")]

    assert not missing, f"queries without a declared pool: {missing}"


def test_pool_members_are_judged_for_their_query(payload):
    """The pool and the judgments must agree, or the metrics are undefined."""
    bad = []
    for qid, query in payload["queries"].items():
        unjudged = [d for d in query["pool"] if d not in query["judgments"]]
        if unjudged:
            bad.append((qid, len(unjudged)))

    assert not bad, f"pool members with no judgment: {bad}"


def test_pools_of_different_topics_do_not_overlap(payload):
    """Overlapping pools would mean one document answers two unrelated needs."""
    by_topic = {}
    for query in payload["queries"].values():
        by_topic.setdefault(query.get("topic") or "", set()).update(query["pool"])

    topics = sorted(by_topic)
    for i, a in enumerate(topics):
        for b in topics[i + 1:]:
            shared = by_topic[a] & by_topic[b]
            assert not shared, f"topics {a!r} and {b!r} share {len(shared)} pool documents"
