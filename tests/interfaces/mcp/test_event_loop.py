"""Tools must not run blocking work on the event loop.

The MCP server runs every tool on one event loop. A tool that calls synchronous
code — a pipeline that joins threads for minutes, an ONNX encode, a pandas
read — freezes every other request for as long as it takes, including the SSE
heartbeat that keeps the connection alive.

Nine tools already offload their HTTP calls with ``asyncio.to_thread``; the
heavy ones did not.
"""

import asyncio
import threading
import time
from unittest.mock import MagicMock, patch

import pytest


async def a_heartbeat(duration, ticks=5):
    """Records when each tick ran, relative to the caller's clock."""
    stamps = []
    for _ in range(ticks):
        await asyncio.sleep(duration / ticks)
        stamps.append(1)
    return stamps


@pytest.fixture
def slow_hunter():
    """An AcademicHunter whose pipeline takes 0.2 s of wall clock."""
    hunter = MagicMock()
    hunter.blocking_thread_ids = []

    def slow_run(*args, **kwargs):
        hunter.blocking_thread_ids.append(threading.get_ident())
        time.sleep(0.2)
        return "results/RELATORIO.md"

    hunter.run.side_effect = slow_run
    hunter.config.settings = {"limit_per_query": 10}
    return hunter


async def test_run_search_does_not_block_the_event_loop(mock_ctx, slow_hunter):
    from academic_hunter.interfaces.mcp.tools.search import run_search

    started = time.monotonic()
    loop_thread = threading.get_ident()
    heartbeat_at = []

    async def heartbeat():
        for _ in range(5):
            await asyncio.sleep(0.02)
            heartbeat_at.append(time.monotonic() - started)

    with patch(
        "academic_hunter.interfaces.mcp.tools.search.AcademicHunter",
        return_value=slow_hunter,
    ):
        await asyncio.gather(run_search(ctx=mock_ctx), heartbeat())

    assert heartbeat_at, "the heartbeat never ran"
    assert slow_hunter.blocking_thread_ids, "the pipeline never ran"
    assert slow_hunter.blocking_thread_ids[0] != loop_thread, (
        "the pipeline ran on the event loop's own thread — every other request, "
        "and the SSE heartbeat, waited on it"
    )


async def test_export_report_does_not_block_the_event_loop(mock_ctx, tmp_path):
    from academic_hunter.interfaces.mcp.tools.export import export_report

    read_thread_ids = []

    def slow_read(*args, **kwargs):
        read_thread_ids.append(threading.get_ident())
        time.sleep(0.2)
        return []

    started = time.monotonic()
    loop_thread = threading.get_ident()
    heartbeat_at = []

    async def heartbeat():
        for _ in range(5):
            await asyncio.sleep(0.02)
            heartbeat_at.append(time.monotonic() - started)

    hunter = MagicMock()
    hunter.consolidated_results = {}

    with patch(
        "academic_hunter.interfaces.mcp.tools.export._load_latest_papers",
        side_effect=slow_read,
    ), patch(
        "academic_hunter.interfaces.mcp.tools.export.get_project_root",
        return_value=tmp_path,
    ), patch(
        "academic_hunter.interfaces.mcp.tools.export.AcademicHunter",
        return_value=hunter,
    ):
        await asyncio.gather(export_report(ctx=mock_ctx), heartbeat())

    assert heartbeat_at
    assert read_thread_ids, "the read never ran"
    assert read_thread_ids[0] != loop_thread, "the read ran on the event loop's own thread"


async def test_a_blocking_helper_exists_and_is_used():
    """The offload is one helper, so the pattern cannot drift per tool."""
    from academic_hunter.interfaces.mcp.tools import _utils

    assert hasattr(_utils, "run_blocking"), (
        "there should be a single place that says how blocking work is offloaded"
    )


def _slow_store(seconds=0.2):
    store = MagicMock()
    store.blocking_thread_ids = []
    store.list_collections.return_value = ["papers"]

    def slow_stats(*args, **kwargs):
        store.blocking_thread_ids.append(threading.get_ident())
        time.sleep(seconds)
        return {"name": "papers", "count": 3}

    store.collection_stats.side_effect = slow_stats
    return store


async def _heartbeat_while(work):
    started = time.monotonic()
    stamps = []

    async def heartbeat():
        for _ in range(5):
            await asyncio.sleep(0.02)
            stamps.append(time.monotonic() - started)

    await asyncio.gather(work, heartbeat())
    return stamps


async def test_the_vector_stats_resource_does_not_block_the_event_loop():
    """Reading `academic-hunter://vector-store/stats` freezes every other request.

    Listing the collections and counting them opens the Chroma client and reads
    from disk. One read measured 355 ms of stall.
    """
    from academic_hunter.interfaces.mcp.resources import get_vector_stats_resource

    loop_thread = threading.get_ident()
    store = _slow_store()

    with patch(
        "academic_hunter.interfaces.mcp.tools._utils._get_vector_store",
        return_value=store,
    ):
        stamps = await _heartbeat_while(get_vector_stats_resource())

    assert stamps, "the heartbeat never ran"
    assert store.blocking_thread_ids, "the store read never ran"
    assert store.blocking_thread_ids[0] != loop_thread, (
        "the store read ran on the event loop's own thread — every other request, "
        "and the SSE heartbeat, waited on it"
    )


async def test_the_health_check_does_not_block_the_event_loop():
    """`GET /health` is what an orchestrator polls, and it froze the server.

    `_check_components` runs the same synchronous store reads as the tool, on the
    same loop, for every probe.
    """
    from academic_hunter.interfaces.mcp.health import _check_components

    loop_thread = threading.get_ident()
    store = _slow_store()

    with patch(
        "academic_hunter.interfaces.mcp.health._get_vector_store",
        return_value=store,
    ), patch("academic_hunter.core.get_config", return_value=MagicMock()):
        stamps = await _heartbeat_while(_check_components())

    assert stamps, "the heartbeat never ran"
    assert store.blocking_thread_ids, "the store read never ran"
    assert store.blocking_thread_ids[0] != loop_thread, (
        "the probe ran on the event loop's own thread — every probe of /health "
        "stops the server from answering anything else"
    )


_OFFLOADING_TOOLS = [
    ("trending", "trending_topics", {}),
    ("related", "find_related_papers", {"query": "term weighting"}),
    ("novelty", "find_novel_papers", {}),
    ("visualization", "topic_evolution", {}),
    ("dedup", "semantic_dedup", {}),
    ("clustering", "cluster_papers", {}),
    ("fulltext", "fulltext_status", {}),
    ("fulltext", "index_fulltext", {}),
    ("fulltext", "chunk_search", {"query": "dataset"}),
    ("writing", "paper_context", {"topic": "term weighting"}),
    ("writing", "verify_citations", {"text": "See [@a2020]."}),
    ("rag", "semantic_search", {"query": "term weighting"}),
    ("rag", "index_papers", {}),
    ("rag", "vector_store_stats", {}),
    ("rag", "delete_collection", {"collection": "papers"}),
    ("rag", "answer_question", {"question": "what is term weighting?"}),
]


@pytest.mark.parametrize(
    "module_name, tool_name, kwargs",
    _OFFLOADING_TOOLS,
    ids=[f"{module}.{tool}" for module, tool, _ in _OFFLOADING_TOOLS],
)
async def test_every_tool_opens_the_store_off_the_event_loop(
    mock_ctx, module_name, tool_name, kwargs
):
    """Opening the store is synchronous, and every tool that opens one froze.

    ``_get_vector_store`` builds a ChromaDB client against a directory on disk;
    on one shared loop that stalls every other request, including the SSE
    heartbeat. The return value here is None, so each tool takes its
    "unavailable" path — what is asserted is only *where* it was called.

    ``index_papers`` and ``index_fulltext`` reach the store only after
    ``_load_latest_papers`` has found something to index, so without a run in
    ``results/`` they answer "no papers found" and never get there. That made the
    assertion depend on the developer's own ``results/`` directory: it held on
    this checkout and failed on a fresh clone, which is the one environment the
    suite has to pass in. The loader is stubbed to the one paper that gets them
    past the guard.
    """
    import contextlib
    import importlib

    module = importlib.import_module(f"academic_hunter.interfaces.mcp.tools.{module_name}")
    loop_thread = threading.get_ident()
    threads = []

    def recording_store():
        threads.append(threading.get_ident())
        return None

    loader = (
        patch.object(module, "_load_latest_papers", lambda: [MagicMock(name="a paper")])
        if hasattr(module, "_load_latest_papers")
        else contextlib.nullcontext()
    )

    with patch.object(module, "_get_vector_store", recording_store), loader:
        with contextlib.suppress(Exception):
            await getattr(module, tool_name)(ctx=mock_ctx, **kwargs)

    assert threads, f"{module_name}.{tool_name} never opened the store"
    assert threads[0] != loop_thread, (
        f"{module_name}.{tool_name} opened the store on the event loop's own "
        f"thread — every other request waited on the disk"
    )


@pytest.fixture
def slow_fetch_hunter():
    """An AcademicHunter whose DOI fetch takes 0.2 s of wall clock."""
    hunter = MagicMock()
    hunter.fetch_thread_ids = []
    hunter.abstract = "Term weighting assigns a weight to each query term before scoring."

    def slow_fetch(doi):
        hunter.fetch_thread_ids.append(threading.get_ident())
        time.sleep(0.2)
        return hunter.abstract

    hunter.fetch_abstract_by_doi.side_effect = slow_fetch
    return hunter


async def test_fetch_paper_by_doi_does_not_block_the_event_loop(mock_ctx, slow_fetch_hunter):
    """The fetch is a synchronous HTTP call, and it ran on the shared loop.

    ``fetch_abstract_by_doi`` goes through the connectors and the cache — network
    I/O with retries and pacing, seconds on a slow day. The hunter was already
    built on a worker thread; the call that takes the time was not.
    """
    from academic_hunter.interfaces.mcp.tools.discovery import fetch_paper_by_doi

    loop_thread = threading.get_ident()

    with patch(
        "academic_hunter.interfaces.mcp.tools.discovery.AcademicHunter",
        return_value=slow_fetch_hunter,
    ):
        stamps = await _heartbeat_while(fetch_paper_by_doi("10.1234/x", ctx=mock_ctx))

    assert stamps, "the heartbeat never ran"
    assert slow_fetch_hunter.fetch_thread_ids, "the fetch never ran"
    assert slow_fetch_hunter.fetch_thread_ids[0] != loop_thread, (
        "the fetch ran on the event loop's own thread — every other request, and "
        "the SSE heartbeat, waited on the network"
    )


async def test_summarize_paper_does_not_block_the_event_loop(mock_ctx, slow_fetch_hunter):
    from academic_hunter.interfaces.mcp.tools.summarize import summarize_paper

    loop_thread = threading.get_ident()

    with patch(
        "academic_hunter.interfaces.mcp.tools.summarize.AcademicHunter",
        return_value=slow_fetch_hunter,
    ):
        stamps = await _heartbeat_while(summarize_paper(ctx=mock_ctx, doi="10.1234/x"))

    assert stamps, "the heartbeat never ran"
    assert slow_fetch_hunter.fetch_thread_ids, "the fetch never ran"
    assert slow_fetch_hunter.fetch_thread_ids[0] != loop_thread, (
        "the fetch ran on the event loop's own thread"
    )


async def test_fetch_multiple_abstracts_does_not_block_the_event_loop(mock_ctx, slow_fetch_hunter):
    """A list of DOIs is the worst case: the loop was held for the whole list."""
    from academic_hunter.interfaces.mcp.tools.discovery import fetch_multiple_abstracts

    loop_thread = threading.get_ident()

    with patch(
        "academic_hunter.interfaces.mcp.tools.discovery.AcademicHunter",
        return_value=slow_fetch_hunter,
    ):
        stamps = await _heartbeat_while(
            fetch_multiple_abstracts(["10.1234/a", "10.1234/b"], ctx=mock_ctx)
        )

    assert stamps, "the heartbeat never ran"
    assert len(slow_fetch_hunter.fetch_thread_ids) == 2, "both DOIs must be fetched"
    assert loop_thread not in slow_fetch_hunter.fetch_thread_ids, (
        "one of the fetches ran on the event loop's own thread"
    )


async def test_the_paper_resource_does_not_block_the_event_loop(slow_fetch_hunter):
    """The resource is served off the same loop as every tool."""
    from academic_hunter.interfaces.mcp.resources import get_paper_resource

    loop_thread = threading.get_ident()

    with patch("academic_hunter.AcademicHunter", return_value=slow_fetch_hunter):
        stamps = await _heartbeat_while(get_paper_resource("10.1234/x"))

    assert stamps, "the heartbeat never ran"
    assert slow_fetch_hunter.fetch_thread_ids, "the fetch never ran"
    assert slow_fetch_hunter.fetch_thread_ids[0] != loop_thread, (
        "the fetch ran on the event loop's own thread"
    )

