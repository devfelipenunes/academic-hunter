"""MCP server for Academic Hunter — FastMCP instance, tool registration, and entry point."""

import json
import logging
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse

from .tools.configuration import (
    read_config,
    update_config,
    list_config_history,
    restore_config_by_id,
)
from .tools.search import run_search, read_latest_report
from .tools.discovery import (
    fetch_paper_by_doi,
    explore_citation_graph,
    fetch_multiple_abstracts,
    quick_topic_discovery,
)
from .tools.obsidian import export_to_obsidian
from .tools.rag import semantic_search, index_papers, vector_store_stats, ask_papers

from .exceptions import ConfigError, VectorStoreError

logger = logging.getLogger("academic_hunter.mcp")


def _setup_logging():
    """Configure structured logging and quieten noisy third-party loggers."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


# ── Health / status ──────────────────────────────────────────────────────────


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

    # Default state
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
        await ctx.warning(f"Config not available: {exc}")

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
        await ctx.warning(f"Vector store not available: {exc}")

    # 3. Last config backup (best-effort)
    try:
        from .memory.sqlite_store import MCPDatabaseManager

        db = MCPDatabaseManager()
        history = db.list_configs(limit=1)
        if history:
            last_backup = history[0].get("timestamp")
    except Exception:
        pass  # non-critical

    data = {
        "status": status,
        "server": "academic-hunter",
        "config_loaded": config_loaded,
        "vector_store": {
            "available": vector_store_available,
            "paper_count": paper_count,
        },
        "last_config_backup": last_backup,
    }

    await ctx.info(f"Server status: {status}")
    return json.dumps(data, ensure_ascii=False)


async def health_check(request):
    """HTTP health-check endpoint for SSE mode."""
    # Reuse the same logic as server_status but without the async Context
    status = "ok"
    config_loaded = True
    vector_store_available = True
    paper_count = 0

    try:
        from academic_hunter.core.infra.config import HunterConfig
        HunterConfig()
    except Exception:
        config_loaded = False
        status = "degraded"

    try:
        from academic_hunter.plugins.vector_stores import ChromaVectorStore
        store = ChromaVectorStore(db_dir="")
        stats = store.collection_stats("papers")
        paper_count = stats.get("count", 0)
    except Exception:
        vector_store_available = False
        if status == "ok":
            status = "degraded"
        elif not config_loaded:
            status = "error"

    return JSONResponse({
        "status": status,
        "server": "academic-hunter",
        "config_loaded": config_loaded,
        "vector_store": {
            "available": vector_store_available,
            "paper_count": paper_count,
        },
    })


# ── Server factory ────────────────────────────────────────────────────────────


def create_mcp_server() -> FastMCP:
    """Instantiate the FastMCP server and register all tools, resources, and prompts."""
    _setup_logging()
    logger.info("Creating Academic Hunter MCP server…")

    mcp = FastMCP(
        "academic-hunter",
        dependencies=["requests", "pandas", "bibtexparser", "chromadb"],
    )

    # ── Tools ──────────────────────────────────────────────────────────────
    mcp.tool()(server_status)

    mcp.tool()(run_search)
    mcp.tool()(read_latest_report)
    mcp.tool()(read_config)
    mcp.tool()(update_config)
    mcp.tool()(list_config_history)
    mcp.tool()(restore_config_by_id)
    mcp.tool()(fetch_paper_by_doi)
    mcp.tool()(explore_citation_graph)
    mcp.tool()(fetch_multiple_abstracts)
    mcp.tool()(quick_topic_discovery)
    mcp.tool()(export_to_obsidian)

    # RAG tools
    mcp.tool()(semantic_search)
    mcp.tool()(index_papers)
    mcp.tool()(vector_store_stats)
    mcp.tool()(ask_papers)

    # ── Custom HTTP routes (SSE mode only) ─────────────────────────────────
    mcp.custom_route("/health", methods=["GET"])(health_check)

    return mcp


# ── CLI entry point ────────────────────────────────────────────────────────────


def run_mcp_server():
    """Run the MCP server (stdio by default; pass ``-t sse`` for HTTP)."""
    import argparse
    import os

    parser = argparse.ArgumentParser(
        description="Academic Hunter MCP Server — connect AI assistants "
        "to academic research tools.",
        epilog="Example: academic-mcp --transport sse --port 8080",
    )
    parser.add_argument(
        "-t", "--transport",
        choices=["stdio", "sse"],
        default=os.environ.get("ACADEMIC_MCP_TRANSPORT", "stdio"),
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("ACADEMIC_MCP_HOST", "127.0.0.1"),
        help="Bind address for SSE mode (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("ACADEMIC_MCP_PORT", "8080")),
        help="Port for SSE mode (default: 8080)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO)",
    )

    args = parser.parse_args()
    logging.getLogger("academic_hunter").setLevel(args.log_level.upper())

    server = create_mcp_server()

    if args.transport == "sse":
        logger.info(
            "Starting MCP server in SSE mode on %s:%s", args.host, args.port
        )
        server.run(transport="sse", host=args.host, port=args.port)
    else:
        logger.info("Starting MCP server in stdio mode…")
        server.run()


if __name__ == "__main__":
    run_mcp_server()
