"""MCP server health check — shared logic for stdio and SSE modes."""

import json
import logging

from mcp.server.fastmcp import Context

logger = logging.getLogger("academic_hunter.mcp")

try:
    from .tools._utils import _get_vector_store
except Exception:
    _get_vector_store = None


async def _check_components() -> dict:
    """Check all components and return status data.

    Off the event loop: every check below opens a file or a client, and this runs
    on the same loop as every tool — `GET /health` is what an orchestrator polls,
    so blocking here stops the server answering anything else.
    """
    from .tools._utils import run_blocking

    return await run_blocking(_probe_components)


def _probe_components() -> dict:
    """The synchronous work behind ``_check_components``.

    Returns a dict with ``status`` (ok/degraded/error), ``config_loaded``,
    ``vector_store`` info, and ``last_config_backup``.
    """
    status = "ok"
    config_loaded = True
    vector_store_available = True
    paper_count = 0
    last_backup = None

    # 1. Config check
    try:
        from academic_hunter.core import get_config

        get_config()
    except Exception as exc:
        config_loaded = False
        status = "degraded"
        logger.warning("Config not available: %s", exc)

    # 2. Vector store check
    if _get_vector_store is None:
        vector_store_available = False
        if status == "ok":
            status = "degraded"
        elif not config_loaded:
            status = "error"
        logger.warning("_get_vector_store import failed")
    else:
        try:
            store = _get_vector_store()
            if store is not None:
                stats = store.collection_stats("papers")
                paper_count = stats.get("count", 0)
            else:
                raise RuntimeError("Vector store returned None")
        except Exception as exc:
            vector_store_available = False
            if status == "ok":
                status = "degraded"
            elif not config_loaded:
                status = "error"
            logger.warning("Vector store not available: %s", exc)

    # 3. Last config backup (best-effort)
    try:
        from .memory.config_backup import MCPDatabaseManager

        db = MCPDatabaseManager()
        history = db.list_configs(limit=1)
        if history:
            last_backup = history[0].get("timestamp")
    except Exception:
        pass  # non-critical

    return {
        "status": status,
        "server": "academic-hunter",
        "config_loaded": config_loaded,
        "vector_store": {
            "available": vector_store_available,
            "paper_count": paper_count,
        },
        "last_config_backup": last_backup,
    }


async def server_status(ctx: Context) -> str:
    """Returns diagnostic information about the MCP server and its dependencies.

    Checks:
    - Can configuration be loaded?
    - Is the vector store (ChromaDB) available?
    - How many papers are indexed?
    - When was the last config backup?

    Returns a JSON string with the overall ``status`` (ok / degraded / error)
    and per-component detail.
    """
    await ctx.info("Checking server status...")
    data = await _check_components()
    await ctx.info(f"Server status: {data['status']}")
    return json.dumps(data, ensure_ascii=False)
