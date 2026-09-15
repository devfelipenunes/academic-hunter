"""Tools must not run blocking work on the event loop.

The MCP server runs every tool on one event loop. A tool that calls synchronous
code — a pipeline that joins threads for minutes, an ONNX encode, a pandas
read — freezes every other request for as long as it takes, including the SSE
heartbeat that keeps the connection alive.

Nine tools already offload their HTTP calls with ``asyncio.to_thread``; the
heavy ones did not.
"""

import asyncio
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
    def slow_run(*args, **kwargs):
        time.sleep(0.2)
        return "results/RELATORIO.md"

    hunter = MagicMock()
    hunter.run.side_effect = slow_run
    hunter.config.settings = {"limit_per_query": 10}
    return hunter


async def test_run_search_does_not_block_the_event_loop(mock_ctx, slow_hunter):
    from academic_hunter.interfaces.mcp.tools.search import run_search

    started = time.monotonic()
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
    # The run takes 0.2 s. If the loop stayed free, every tick lands well before
    # it finishes; if the tool blocked, they all pile up after.
    assert max(heartbeat_at) < 0.15, (
        f"the event loop was blocked for {max(heartbeat_at):.2f}s — every other "
        f"request, and the SSE heartbeat, waited on the pipeline"
    )


async def test_export_report_does_not_block_the_event_loop(mock_ctx, tmp_path):
    from academic_hunter.interfaces.mcp.tools.export import export_report

    def slow_read(*args, **kwargs):
        time.sleep(0.2)
        return []

    started = time.monotonic()
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
    assert max(heartbeat_at) < 0.15, "the event loop was blocked while reading"


async def test_a_blocking_helper_exists_and_is_used():
    """The offload is one helper, so the pattern cannot drift per tool."""
    from academic_hunter.interfaces.mcp.tools import _utils

    assert hasattr(_utils, "run_blocking"), (
        "there should be a single place that says how blocking work is offloaded"
    )


# ── resources and the health route ──────────────────────────────────────────
#
# These are `async def` with no `await` anywhere: every call they make is
# synchronous, and it ran on the loop that serves everything else. The tools were
# covered by the tests above; the resource layer and the route `/health` calls
# were not.


def _slow_store(seconds=0.2):
    store = MagicMock()
    store.list_collections.return_value = ["papers"]
    store.collection_stats.side_effect = lambda *a, **k: (
        time.sleep(seconds) or {"name": "papers", "count": 3}
    )
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

    with patch(
        "academic_hunter.interfaces.mcp.tools._utils._get_vector_store",
        return_value=_slow_store(),
    ):
        stamps = await _heartbeat_while(get_vector_stats_resource())

    assert stamps, "the heartbeat never ran"
    assert max(stamps) < 0.15, (
        f"the event loop was blocked for {max(stamps):.2f}s — every other request, "
        f"and the SSE heartbeat, waited on the vector store"
    )


async def test_the_health_check_does_not_block_the_event_loop():
    """`GET /health` is what an orchestrator polls, and it froze the server.

    `_check_components` runs the same synchronous store reads as the tool, on the
    same loop, for every probe.
    """
    from academic_hunter.interfaces.mcp.health import _check_components

    with patch(
        "academic_hunter.interfaces.mcp.health._get_vector_store",
        return_value=_slow_store(),
    ), patch("academic_hunter.core.get_config", return_value=MagicMock()):
        stamps = await _heartbeat_while(_check_components())

    assert stamps, "the heartbeat never ran"
    assert max(stamps) < 0.15, (
        f"the event loop was blocked for {max(stamps):.2f}s — every probe of "
        f"/health stops the server from answering anything else"
    )
