"""MCP server health check — shared logic for stdio and SSE modes."""

import json
import logging

logger = logging.getLogger("academic_hunter.mcp")


def _check_components() -> dict:
    """Check all components and return status data.

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
        from academic_hunter.core.infra.config import HunterConfig

        HunterConfig()
    except Exception as exc:
        config_loaded = False
        status = "degraded"
        logger.warning("Config not available: %s", exc)

    # 2. Vector store check
    try:
        from academic_hunter.plugins.vector_stores import ChromaVectorStore

        store = ChromaVectorStore(db_dir="")
        stats = store.collection_stats("papers")
        paper_count = stats.get("count", 0)
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


async def server_status(ctx) -> str:
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
    data = _check_components()
    await ctx.info(f"Server status: {data['status']}")
    return json.dumps(data, ensure_ascii=False)
