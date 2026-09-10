"""Tests for the opt-in full-text ingest step.

The step runs between a finished run and its report, so the property under test
throughout is that it never takes the run down with it.
"""

import threading

import pytest

from academic_hunter.core.pipeline.steps import IngestFullTextStep
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
    """Satisfies `ChunkStorePort` structurally, and records what it was given."""

    def __init__(self, result=True):
        self.result = result
        self.indexed = []

    def index_chunks(self, chunks, collection_name="paper_chunks"):
        self.indexed.append(list(chunks))
        return self.result

    def query_chunks(self, prompt, top_k=10, collection_name="paper_chunks"):
        return []

    def has_chunks(self, parent_id, collection_name="paper_chunks"):
        return False

    def delete_chunks(self, parent_id, collection_name="paper_chunks"):
        return 0


def make_step(papers=None, settings=None, fetcher="default", store="default"):
    hunter = type("H", (), {})()
    hunter.config = type("C", (), {})()
    hunter.config.fulltext_config = lambda: {
        "enabled": True,
        "email": "me@example.com",
        "max_papers": 200,
        "time_budget_seconds": 900,
        **(settings or {}),
    }
    hunter.full_text_fetcher = (
        (lambda doi: ExtractedDocument(text=LONG_TEXT, page_count=2))
        if fetcher == "default"
        else fetcher
    )
    hunter.pipeline = type("P", (), {})()
    hunter.pipeline.vector_store = FakeChunkStore() if store == "default" else store
    hunter.lock = threading.RLock()
    hunter.state = type("S", (), {})()
    hunter.state.stats = {}
    hunter.consolidated_results = (
        {"a": {"Title": "A study", "DOI": "10.1/a"}} if papers is None else papers
    )
    return IngestFullTextStep(hunter)


# ── when it must do nothing ─────────────────────────────────────────────────


def test_disabled_by_default():
    step = make_step(settings={"enabled": False})
    step.hunter.consolidated_results["a"]["_full_text_status"] = "untouched"

    step.run()

    assert step.hunter.consolidated_results["a"]["_full_text_status"] == "untouched"
    assert "full_text" not in step.hunter.state.stats


def test_no_fetcher_wired_is_a_no_op():
    step = make_step(fetcher=None)

    step.run()

    assert "_full_text_status" not in step.hunter.consolidated_results["a"]


def test_a_store_that_cannot_hold_chunks_is_a_no_op():
    """Not every vector store implements the chunk capability."""
    step = make_step(store=object())

    step.run()

    assert "_full_text_status" not in step.hunter.consolidated_results["a"]


def test_no_papers_is_a_no_op():
    step = make_step(papers={})

    step.run()  # must not raise

    assert step.hunter.state.stats == {}


# ── the happy path ──────────────────────────────────────────────────────────


def test_a_paper_is_fetched_chunked_and_indexed():
    step = make_step()

    step.run()

    paper = step.hunter.consolidated_results["a"]
    assert paper["_full_text_status"] == "obtained"
    indexed = step.hunter.pipeline.vector_store.indexed[0]
    assert indexed, "no chunks were indexed"
    assert all(c["parent_id"] == "doi:10.1/a" for c in indexed)
    assert step.hunter.state.stats["full_text"]["obtained"] == 1


def test_chunks_carry_their_section_and_offsets():
    step = make_step()

    step.run()

    indexed = step.hunter.pipeline.vector_store.indexed[0]
    sections = {c["section"] for c in indexed}
    assert {"abstract", "introduction", "method"} <= sections
    assert all(c["chunk_id"].startswith("doi:10.1/a::") for c in indexed)


# ── each failure gets its own status ────────────────────────────────────────


def test_no_open_access_is_recorded_as_such():
    """It is the common case, not a failure, and the two must not be conflated."""
    def fetcher(doi):
        raise NoOpenAccessVersion(doi)

    step = make_step(fetcher=fetcher)
    step.run()

    assert step.hunter.consolidated_results["a"]["_full_text_status"] == "no_open_access"
    assert step.hunter.state.stats["full_text"]["no_open_access"] == 1


def test_a_download_failure_is_recorded_as_such():
    def fetcher(doi):
        raise FullTextTransientError("403 from the publisher")

    step = make_step(fetcher=fetcher)
    step.run()

    assert step.hunter.consolidated_results["a"]["_full_text_status"] == "download_failed"


def test_a_pdf_without_a_text_layer_is_recorded_as_such():
    def fetcher(doi):
        return ExtractedDocument(text="", page_count=10, has_text_layer=False)

    step = make_step(fetcher=fetcher)
    step.run()

    assert step.hunter.consolidated_results["a"]["_full_text_status"] == "no_text_layer"


def test_a_paper_without_a_doi_never_reaches_the_network():
    def fetcher(doi):
        raise AssertionError("should not have been called")

    step = make_step(papers={"a": {"Title": "No DOI here"}}, fetcher=fetcher)
    step.run()

    assert step.hunter.consolidated_results["a"]["_full_text_status"] == "no_doi"


def test_an_unexpected_error_does_not_escape():
    def fetcher(doi):
        raise RuntimeError("something nobody predicted")

    step = make_step(fetcher=fetcher)
    step.run()  # must not raise

    assert step.hunter.consolidated_results["a"]["_full_text_status"] == "download_failed"


def test_a_store_failure_leaves_the_run_alive():
    def fetcher(doi):
        return ExtractedDocument(text=LONG_TEXT, page_count=2)

    step = make_step(fetcher=fetcher, store=FakeChunkStore(result=False))
    step.run()  # must not raise

    assert step.hunter.consolidated_results["a"]["_full_text_status"] == "download_failed"


# ── a broken configuration stops the whole step ─────────────────────────────


def test_a_config_error_abandons_the_rest_of_the_batch():
    """Every remaining call would fail the same way, so they are not attempted."""
    calls = []

    def fetcher(doi):
        calls.append(doi)
        raise FullTextConfigError("Unpaywall refused the contact e-mail")

    papers = {f"p{i}": {"Title": f"T{i}", "DOI": f"10.1/{i}"} for i in range(5)}
    step = make_step(papers=papers, fetcher=fetcher)
    step.run()

    statuses = [p["_full_text_status"] for p in step.hunter.consolidated_results.values()]
    assert len(calls) == 1, f"kept trying after a config error: {calls}"
    # The one that failed was attempted; the four after it were not.
    assert statuses.count("download_failed") == 1
    assert statuses.count("not_attempted") == 4
    assert step.hunter.state.stats["full_text"]["not_attempted"] == 4


def test_the_paper_budget_is_respected_and_reported():
    papers = {f"p{i}": {"Title": f"T{i}", "DOI": f"10.1/{i}"} for i in range(10)}
    step = make_step(papers=papers, settings={"max_papers": 3})
    step.run()

    counters = step.hunter.state.stats["full_text"]
    assert counters["obtained"] == 3
    assert counters["not_attempted"] == 7, "a skipped paper must not look like a missing OA copy"


def test_the_time_budget_is_respected():
    import time

    # The budget is whole seconds, so the work has to overshoot one by a wide
    # margin: 50 papers at 50 ms is ~2.5 s of work against a 1 s budget.
    def slow_fetcher(doi):
        time.sleep(0.05)
        return ExtractedDocument(text=LONG_TEXT, page_count=2)

    papers = {f"p{i}": {"Title": f"T{i}", "DOI": f"10.1/{i}"} for i in range(50)}
    step = make_step(papers=papers, fetcher=slow_fetcher, settings={"time_budget_seconds": 1})
    step.run()

    counters = step.hunter.state.stats["full_text"]
    assert counters["not_attempted"] > 0, "the budget never triggered"
    assert counters["obtained"] + counters["not_attempted"] == 50, "a paper lost its status"
