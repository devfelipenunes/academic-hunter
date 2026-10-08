"""Validity checks for the blockchain x AI pool and the page that grades it.

The pool is the population a human is asked to judge, and the page is what they
judge it in. Both are generated, so both can go stale silently: a pool
re-selected from a new run while the page still embeds the old documents would
collect grades for papers that are no longer in the collection, and the
calibration would measure against them without saying so.

The id is the join between all three — the pool, the page, and the run's score
distribution, which ``sweep_threshold`` indexes by ``doc_id_for(title, doi)``.
An id that does not match the document it names is a judgment that lands on no
paper, and precision quietly counts it as a miss.
"""

import csv
import json
import re
from pathlib import Path

import pytest

from academic_hunter.core.evaluation.qrels import doc_id_for
from academic_hunter.core.models.utils import doi_from_url

ROOT = Path(__file__).resolve().parent.parent
POOL_PATH = ROOT / "evaluation" / "pool_candidates_blockchain_ai.json"
PAGE_PATH = ROOT / "evaluation" / "pool_grading_page.html"
QRELS_PATH = ROOT / "evaluation" / "qrels_blockchain_ai.json"


@pytest.fixture(scope="module")
def pool():
    return json.loads(POOL_PATH.read_text(encoding="utf-8"))


def test_the_pool_is_non_empty_and_keyed_by_its_own_ids(pool):
    documents = pool["documents"]

    assert documents, "the pool has no documents to judge"
    for doc_id, doc in documents.items():
        assert doc_id == doc_id_for(str(doc.get("title") or ""), str(doc.get("doi") or "")), (
            f"{doc_id!r} is not the id doc_id_for derives from that document, so a "
            "judgment on it would score against no paper in the run"
        )


def test_the_pool_records_the_query_it_was_selected_for(pool):
    """Without the information need there is nothing to grade against.

    A judge asked to rate relevance with no stated query rates agreement with
    the topic, and the resulting precision is a measurement of a different
    question from the one the run was ordered by.
    """
    assert str(pool.get("ranking_query") or "").strip(), (
        "the pool names its source run but not the query that run was ordered by"
    )
    assert pool.get("source_csv"), "the pool does not name the run it came from"


def test_the_page_embeds_exactly_the_pool_it_grades(pool):
    """The page is generated from the pool, and has to still agree with it.

    Pinned because the failure is silent in both directions: a page built from
    an older pool collects grades for documents that were dropped, and a page
    built from a newer one asks about documents the run never scored.
    """
    html = PAGE_PATH.read_text(encoding="utf-8")
    embedded = json.loads(re.search(r"^const DOCS = (.*);$", html, re.M).group(1))

    assert sorted(row["id"] for row in embedded) == sorted(pool["documents"]), (
        "the page embeds a different set of documents from the pool"
    )
    assert len(embedded) == len(pool["documents"]), "the page repeats a document"
    assert json.loads(re.search(r"^const QUERY = (.*);$", html, re.M).group(1)) == pool["ranking_query"]


def test_the_page_shows_the_whole_abstract_it_was_given(pool):
    """A truncated abstract is a judgment on a different document."""
    html = PAGE_PATH.read_text(encoding="utf-8")
    embedded = json.loads(re.search(r"^const DOCS = (.*);$", html, re.M).group(1))
    by_id = {row["id"]: row for row in embedded}

    for doc_id, doc in pool["documents"].items():
        assert by_id[doc_id]["abstract"] == str(doc.get("abstract") or "")
        assert by_id[doc_id]["title"] == str(doc.get("title") or "")


def test_the_pool_was_re_keyed_after_dois_started_being_resolved(pool):
    """Um pool escrito antes do lote Q fica com ids que o run já não produz.

    O id é `doc_id_for(title, doi)`, e o run passou a gravar o DOI que o URL do
    arXiv implica. Um pool que não tenha sido reconstruído depois disso continua
    internamente coerente — os testes acima passam — e ao mesmo tempo aponta
    para chaves que a distribuição de pontuações já não tem, que é a forma como
    um julgamento se perde sem que nada o diga.

    O CSV do run não está versionado, logo o teste salta numa cópia limpa. O que
    ele pina é o pool **deste** repositório, contra o run de onde ele saiu.
    """
    source_csv = ROOT / str(pool.get("source_csv") or "")
    if not source_csv.exists():
        pytest.skip(f"the run's own CSV is not here: {pool.get('source_csv')}")

    with open(source_csv, newline="", encoding="utf-8") as handle:
        by_title = {
            " ".join((row.get("Title") or "").split()).lower(): row
            for row in csv.DictReader(handle)
        }

    for doc_id, doc in pool["documents"].items():
        row = by_title[" ".join(str(doc.get("title") or "").split()).lower()]
        doi = str(row.get("DOI") or "").strip() or doi_from_url(row.get("URL"))
        assert doc_id == doc_id_for(row.get("Title"), doi), (
            f"{doc_id!r} is the id of a pool built before the run resolved the "
            f"DOI {doi!r}; rebuild the pool (evaluation/rebuild_pool.py) before judging it"
        )
        assert str(doc.get("doi") or "") == doi


@pytest.mark.skipif(not QRELS_PATH.exists(), reason="the pool has not been judged yet")
def test_a_judged_pool_only_grades_documents_it_contains(pool):
    """The same check the shipped pilot collection gets, for the same reason."""
    payload = json.loads(QRELS_PATH.read_text(encoding="utf-8"))
    judged = {d for q in payload["queries"].values() for d in q["judgments"]}

    assert not (judged - set(pool["documents"])), (
        f"judged but not in the pool: {sorted(judged - set(pool['documents']))[:3]}"
    )
    for query in payload["queries"].values():
        assert query["text"].strip(), "a judged query carries no text"
        assert all(isinstance(g, int) and 0 <= g <= 2 for g in query["judgments"].values()), (
            "grades must be the 0/1/2 the pilot collection uses"
        )
