"""Validity checks for the shipped full-text coverage artefact.

Checked every run for the same reason the judged collection is: divergence
between the artefact and the code turns a measurement into a claim. Statuses are
checked against ``core.fulltext.ingest.STATUSES``, not a copy.
"""

import json
from pathlib import Path

import pytest

from academic_hunter.core.evaluation import load_qrels
from academic_hunter.core.evaluation.qrels import pooled_documents
from academic_hunter.core.fulltext.ingest import STATUSES

ROOT = Path(__file__).resolve().parent.parent
COVERAGE_PATH = ROOT / "papers" / "evaluation" / "fulltext_coverage.json"
QRELS_PATH = ROOT / "papers" / "evaluation" / "qrels_pilot_genre_analysis.json"


@pytest.fixture(scope="module")
def payload():
    return json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))


def test_the_artefact_exists_and_parses():
    assert COVERAGE_PATH.exists(), (
        "regenerate it with papers/experiments/fulltext_eval.py"
    )
    assert isinstance(json.loads(COVERAGE_PATH.read_text(encoding="utf-8")), dict)


def test_every_document_it_names_is_a_judged_document(payload):
    """An id that is not in the qrels describes a document nothing will rank."""
    judged = pooled_documents(load_qrels(QRELS_PATH))
    unknown = sorted(set(payload["per_document"]) - judged)
    assert not unknown, f"not in the judged collection: {unknown[:3]}"


def test_the_counters_add_up_to_the_documents(payload):
    counters = payload.get("counters") or {}
    if not counters:
        pytest.skip("no fetch has been run yet; the artefact only carries the ids")
    assert sum(counters.values()) == payload["documents"]


def test_every_status_is_one_the_ingest_can_produce(payload):
    written = {row["status"] for row in payload["per_document"].values()}
    assert written <= set(STATUSES), f"unknown status: {sorted(written - set(STATUSES))}"


def test_the_totals_agree_with_the_per_document_rows(payload):
    rows = payload["per_document"].values()
    with_chunks = [row for row in rows if row["chunks"] > 0]

    assert payload["documents_with_chunks"] == len(with_chunks)
    assert payload["chunks_total"] == sum(row["chunks"] for row in rows)


def test_a_document_with_chunks_was_actually_obtained(payload):
    """Chunks cannot exist without a fetched document, so the status must say so."""
    for doc_id, row in payload["per_document"].items():
        if row["chunks"]:
            assert row["status"] in ("obtained", "already_indexed"), (
                f"{doc_id} has {row['chunks']} chunks but is marked {row['status']!r}"
            )


def test_no_document_without_a_doi_is_reported_as_obtained(payload):
    """The structural ceiling, and the thing it must never be confused with.

    A document with no DOI cannot be addressed at all — that is not a failed
    download and not a missing open-access copy. It may also be `not_attempted`
    when a run stopped at its budget before reaching it, which is why the
    assertion is on what it must *not* be.
    """
    for doc_id, row in payload["per_document"].items():
        if not row["doi"].strip():
            assert row["chunks"] == 0, f"{doc_id} has no DOI yet has chunks"
            assert row["status"] in ("no_doi", "not_attempted"), (
                f"{doc_id} has no DOI but is marked {row['status']!r}"
            )


def test_the_per_topic_ceiling_is_not_exceeded(payload):
    """`with_chunks` can never beat `with_doi`: only addressed papers can be fetched."""
    for topic, row in payload["per_topic"].items():
        assert row["with_chunks"] <= row["with_doi"] <= row["pool"], topic
