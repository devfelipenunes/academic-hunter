"""Tests for the shared full-text ingest loop.

The loop has two callers — the pipeline step and the ``index_fulltext`` MCP
tool — which is why it lives in ``core`` instead of inside the step. What is
under test here is the whole failure matrix, because this is the only place it
exists now: a second copy of it would drift from this one in silence.
"""

import pytest

from academic_hunter.core.evaluation.qrels import doc_id_for
from academic_hunter.core.fulltext.ingest import STATUSES, ingest_full_text
from academic_hunter.core.ports.fulltext import (
    ExtractedDocument,
    FullTextConfigError,
    FullTextTransientError,
    NoOpenAccessVersion,
)

LONG_TEXT = (
    "Abstract\nThis paper studies ledgers.\n\n"
    "1. Introduction\n" + " ".join(f"alpha{i}" for i in range(300)) + "\n\n"
    "2. Methods\n" + " ".join(f"beta{i}" for i in range(300))
)


class FakeChunkStore:
    """Satisfies ``ChunkStorePort`` structurally, and records what it was given."""

    def __init__(self, result=True, already=()):
        self.result = result
        self.already = set(already)
        self.indexed = []
        self.indexed_collections = []
        self.deleted = []
        self.kept = []
        self.asked = []

    def index_chunks(self, chunks, collection_name="paper_chunks"):
        self.indexed.append(list(chunks))
        self.indexed_collections.append(collection_name)
        return self.result

    def query_chunks(self, prompt, top_k=10, collection_name="paper_chunks"):
        return []

    def has_chunks(self, parent_id, collection_name="paper_chunks"):
        self.asked.append(parent_id)
        return parent_id in self.already

    def delete_chunks(self, parent_id, collection_name="paper_chunks", *, keep_ids=()):
        self.deleted.append(parent_id)
        self.kept.append(set(keep_ids))
        return 1


def document(text=LONG_TEXT, has_text_layer=True):
    return ExtractedDocument(text=text, page_count=2, has_text_layer=has_text_layer)


def config(**overrides):
    return {
        "enabled": True,
        "email": "me@example.com",
        "max_papers": 200,
        "time_budget_seconds": 900,
        **overrides,
    }


def paper(title="A study", doi="10.1/a"):
    return {"Title": title, "DOI": doi}


def fetcher_returning(*outcomes):
    """A fetcher that walks ``outcomes``: an exception instance or a document."""
    calls = []

    def fetch(doi):
        calls.append(doi)
        outcome = outcomes[min(len(calls) - 1, len(outcomes) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    fetch.calls = calls
    return fetch


# ── the happy path, and what it leaves behind ───────────────────────────────


def test_every_paper_gets_a_status_and_the_counters_add_up():
    papers = [paper("One", "10.1/a"), paper("Two", "10.1/b"), paper("Three", "")]
    store = FakeChunkStore()

    counters = ingest_full_text(papers, fetcher_returning(document()), store, config())

    assert sum(counters.values()) == len(papers)
    assert [p["_full_text_status"] for p in papers] == ["obtained", "obtained", "no_doi"]
    assert set(counters) == set(STATUSES), "a status the vocabulary does not know"


def test_the_chunk_carries_the_identity_of_its_paper():
    """`chunk_search` names the paper from the chunk: the parent_id is an id.

    Without this the tool would have to resolve ``doi:…``/``title:…`` against
    the last run's CSV, which is not versioned and does get cleaned.
    """
    store = FakeChunkStore()
    papers = [paper("Ledgers in practice", "10.1/a")]

    ingest_full_text(papers, fetcher_returning(document()), store, config())

    records = store.indexed[0]
    assert records, "nothing was indexed"
    for record in records:
        assert record["title"] == "Ledgers in practice"
        assert record["doi"] == "10.1/a"
        assert "year" in record
        assert record["parent_id"] == doc_id_for("Ledgers in practice", "10.1/a")


def test_a_stale_source_from_a_previous_run_is_cleared():
    """The dataset a tool reads back carries the last run's columns.

    Without clearing it, a paper whose re-fetch failed would still report the
    source that delivered it last time — provenance for an attempt that never
    reached a source.
    """
    stale = {**paper(), "_full_text_source": "UnpaywallPdfSource"}

    ingest_full_text(
        [stale], fetcher_returning(FullTextTransientError("503")), FakeChunkStore(), config()
    )

    assert stale["_full_text_status"] == "download_failed"
    assert "_full_text_source" not in stale


def test_a_paper_without_a_doi_costs_no_request():
    fetch = fetcher_returning(document())

    counters = ingest_full_text([paper("No doi", "")], fetch, FakeChunkStore(), config())

    assert counters["no_doi"] == 1
    assert fetch.calls == [], "a request was spent on a paper that cannot be addressed"


# ── idempotence ─────────────────────────────────────────────────────────────


def test_an_indexed_paper_is_skipped_without_being_fetched():
    parent_id = doc_id_for("A study", "10.1/a")
    store = FakeChunkStore(already={parent_id})
    fetch = fetcher_returning(document())

    counters = ingest_full_text([paper()], fetch, store, config())

    assert counters["already_indexed"] == 1
    assert counters["obtained"] == 0
    assert fetch.calls == [], "an indexed paper was downloaded again"
    assert store.indexed == []


def test_force_replaces_the_chunks_instead_of_skipping():
    parent_id = doc_id_for("A study", "10.1/a")
    store = FakeChunkStore(already={parent_id})

    counters = ingest_full_text([paper()], fetcher_returning(document()), store, config(), force=True)

    assert counters["obtained"] == 1
    assert store.indexed, "force did not reindex"
    assert store.deleted == [parent_id], (
        "upserting alone leaves the old chunk ids behind when a paper now "
        "yields fewer chunks"
    )


def test_a_force_that_fails_keeps_the_chunks_that_were_there():
    """Measured: deleting before the fetch lost seven chunks on a flaky network.

    `force` on three papers removed what the index already held and could not put
    it back, because two of the three re-fetches failed. The replacement is
    deleted and written together, after the text is in hand.
    """
    parent_id = doc_id_for("A study", "10.1/a")
    store = FakeChunkStore(already={parent_id})

    counters = ingest_full_text(
        [paper()],
        fetcher_returning(FullTextTransientError("503")),
        store,
        config(),
        force=True,
    )

    assert counters["download_failed"] == 1
    assert store.deleted == [], "the old chunks were destroyed for nothing"
    assert store.indexed == []


def test_a_force_whose_indexing_fails_keeps_the_chunks_that_were_there():
    """The other half of the reindex hazard: the document arrives, and then the
    store refuses the batch.

    `test_a_force_that_fails_keeps_the_chunks_that_were_there` covers the fetch
    failing. Here the fetch succeeds, so a delete ordered before the index would
    already have run — and the paper would be left with nothing at all.
    """
    parent_id = doc_id_for("A study", "10.1/a")
    store = FakeChunkStore(already={parent_id}, result=False)

    counters = ingest_full_text(
        [paper()], fetcher_returning(document()), store, config(), force=True
    )

    assert counters["download_failed"] == 1
    assert store.deleted == [], "the old chunks were destroyed for a batch the store refused"


def test_a_successful_force_removes_only_what_the_new_version_lacks():
    """Indexing upserts by chunk id, so the surplus is what has to be named."""
    parent_id = doc_id_for("A study", "10.1/a")
    store = FakeChunkStore(already={parent_id})

    ingest_full_text([paper()], fetcher_returning(document()), store, config(), force=True)

    assert store.deleted == [parent_id]
    assert store.kept[-1] == {c["chunk_id"] for c in store.indexed[-1]}, (
        "the store was told to delete without being told what the new version kept"
    )


def test_the_collection_can_be_redirected():
    """The evaluation indexes into its own collection, never the shipped one."""
    store = FakeChunkStore()

    ingest_full_text(
        [paper()], fetcher_returning(document()), store, config(),
        collection_name="paper_chunks_eval",
    )

    assert store.indexed_collections == ["paper_chunks_eval"]


# ── degradation: each case counted, nothing propagated ──────────────────────


@pytest.mark.parametrize(
    "outcome,expected",
    [
        (NoOpenAccessVersion("no OA copy"), "no_open_access"),
        (FullTextTransientError("503"), "download_failed"),
        (document(has_text_layer=False), "no_text_layer"),
        (document(text="   "), "no_text_layer"),
        # Text extracted, but nothing in it looks like a section. Distinct from
        # `no_text_layer` on purpose: that one points at OCR, this one at the
        # extractor, and they are different repairs.
        (document(text="just one long run of prose " * 50), "no_sections"),
    ],
)
def test_each_failure_has_its_own_status(outcome, expected):
    papers = [paper()]

    counters = ingest_full_text(papers, fetcher_returning(outcome), FakeChunkStore(), config())

    assert papers[0]["_full_text_status"] == expected
    assert counters[expected] == 1


def test_an_unexpected_error_is_contained():
    papers = [paper()]

    counters = ingest_full_text(
        papers, fetcher_returning(RuntimeError("boom")), FakeChunkStore(), config()
    )

    assert counters["download_failed"] == 1
    assert papers[0]["_full_text_status"] == "download_failed"


def test_a_failure_keeps_the_reason():
    """`download_failed` covers three situations, and only one is worth retrying.

    Measured on the judged collection: 30 of 83 addressable documents land here,
    some because the open-access copy is only a landing page and some because the
    publisher refuses a non-browser client. A bare count cannot be acted on.
    """
    papers = [paper()]

    ingest_full_text(
        papers,
        fetcher_returning(FullTextTransientError("http://x did not return a PDF")),
        FakeChunkStore(),
        config(),
    )

    assert "did not return a PDF" in papers[0]["_full_text_error"]


def test_a_very_long_reason_is_truncated():
    papers = [paper()]

    ingest_full_text(
        papers, fetcher_returning(RuntimeError("x" * 5000)), FakeChunkStore(), config()
    )

    assert len(papers[0]["_full_text_error"]) == 300


def test_a_bad_config_fails_each_paper_without_raising():
    """The ingest cannot tell a global config problem from a per-DOI one.

    The sources in the chain do not share configuration, so a rejected e-mail is
    evidence about Unpaywall and nothing about Europe PMC. Every paper is
    attempted and marked, and the time budget is what stops a run going nowhere.
    """
    papers = [paper("One", "10.1/a"), paper("Two", "10.1/b"), paper("Three", "10.1/c")]
    fetch = fetcher_returning(FullTextConfigError("invalid e-mail"))

    counters = ingest_full_text(papers, fetch, FakeChunkStore(), config())

    assert counters["download_failed"] == 3
    assert counters["not_attempted"] == 0
    assert len(fetch.calls) == 3
    assert all(p["_full_text_error"] for p in papers), "the reason is kept per paper"


def test_a_config_error_on_one_paper_does_not_abandon_the_rest():
    """A config error out of the chain means every source failed for **this** doi.

    The sources do not share configuration, so that says nothing about the next
    paper — `ChainFullTextSource` documents exactly this ("an unusable contact
    address breaks Unpaywall and leaves Europe PMC untouched"). Reading it as a
    global failure is how one rejected e-mail silenced the full-text of an entire
    run, including papers another source would have served.
    """
    papers = [paper("One", "10.1/a"), paper("Two", "10.1/b")]
    fetch = fetcher_returning(FullTextConfigError("invalid e-mail"), document())

    counters = ingest_full_text(papers, fetch, FakeChunkStore(), config())

    assert counters["not_attempted"] == 0, "a per-paper failure abandoned the run"
    assert counters["download_failed"] == 1
    assert counters["obtained"] == 1
    assert papers[1]["_full_text_status"] == "obtained"
    assert len(fetch.calls) == 2, "the second paper was never attempted"


def test_a_store_that_cannot_hold_chunks_is_not_an_error():
    class NotAChunkStore:
        pass

    papers = [paper()]

    counters = ingest_full_text(papers, fetcher_returning(document()), NotAChunkStore(), config())

    assert counters == {status: 0 for status in STATUSES}
    assert "_full_text_status" not in papers[0]


def test_an_indexing_failure_is_reported_as_a_failed_download():
    papers = [paper()]

    counters = ingest_full_text(
        papers, fetcher_returning(document()), FakeChunkStore(result=False), config()
    )

    assert counters["download_failed"] == 1


# ── budget ──────────────────────────────────────────────────────────────────


def test_the_paper_budget_leaves_the_rest_untouched():
    papers = [paper(f"P{i}", f"10.1/{i}") for i in range(5)]
    fetch = fetcher_returning(document())

    counters = ingest_full_text(papers, fetch, FakeChunkStore(), config(max_papers=2))

    assert counters["obtained"] == 2
    assert counters["not_attempted"] == 3
    assert len(fetch.calls) == 2


def test_a_skipped_paper_does_not_consume_the_budget():
    """Skipping is free, so it must not push real work out of the budget."""
    already = {doc_id_for("P0", "10.1/0"), doc_id_for("P1", "10.1/1")}
    papers = [paper(f"P{i}", f"10.1/{i}") for i in range(4)]
    fetch = fetcher_returning(document())

    counters = ingest_full_text(
        papers, fetch, FakeChunkStore(already=already), config(max_papers=2)
    )

    assert counters["already_indexed"] == 2
    assert counters["obtained"] == 2, "the indexed pair ate the budget"
    assert len(fetch.calls) == len(papers) - len(already)


def test_the_time_budget_stops_the_batch(monkeypatch):
    clock = iter([0.0, 0.0, 0.0, 10_000.0, 10_000.0])
    monkeypatch.setattr(
        "academic_hunter.core.fulltext.ingest.time.monotonic", lambda: next(clock)
    )
    papers = [paper(f"P{i}", f"10.1/{i}") for i in range(3)]
    fetch = fetcher_returning(document())

    counters = ingest_full_text(
        papers, fetch, FakeChunkStore(), config(time_budget_seconds=60)
    )

    assert counters["not_attempted"] > 0, "the budget never triggered"
    assert sum(counters.values()) == len(papers)
