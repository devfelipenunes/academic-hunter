"""MCP server for Academic Hunter — FastMCP instance, tool registration, and entry point."""

import json
import logging
from pathlib import Path

from mcp.server.fastmcp import Context, FastMCP
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
from .tools.europepmc import search_europepmc
from .tools.obsidian import export_to_obsidian
from .tools.analysis import trending_topics, compare_papers, export_report, find_novel_papers, find_related_papers
from .tools.rag import semantic_search, index_papers, vector_store_stats, ask_papers, answer_question
from .tools.clustering import cluster_papers
from .tools.citations import get_citation_count, get_citing_papers

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


# ── Resource functions ─────────────────────────────────────────────────────────


async def _get_config_resource() -> str:
    """Return the current Academic Hunter configuration as a JSON string.

    Exposes settings, anchors, technical strings/weights, context rules,
    keyword-only terms, and blocked sources in a machine-readable format.
    """
    import json as _json

    from academic_hunter.core.infra.config import HunterConfig

    config = HunterConfig()
    data = {
        "settings": config.settings,
        "anchors": config.anchors,
        "technical_strings": config.tech_strings,
        "technical_weights": config.tech_weights,
        "context_rules": config.context_rules,
        "keyword_only_terms": config.keyword_only_terms,
        "keyword_only_category": config.keyword_only_category,
        "blocked_sources": list(config.blocked_sources),
    }
    return _json.dumps(data, ensure_ascii=False, indent=2)


async def _get_latest_report_resource() -> str:
    """Return the content of the most recently generated report (.md).

    Scans the ``results/`` directory for Markdown files sorted by
    modification time (newest first).  Content is truncated to 10 000
    characters.  Returns ``"No report available"`` when no report exists.
    """
    from .tools._utils import get_project_root

    results_dir = get_project_root() / "results"
    if not results_dir.exists():
        return "No report available"

    md_files = sorted(
        results_dir.glob("**/*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not md_files:
        return "No report available"

    content = md_files[0].read_text(encoding="utf-8", errors="replace")
    return content[:10000]


async def _get_vector_stats_resource() -> str:
    """Return vector-store statistics (collections, paper counts) as JSON.

    Gracefully handles a missing or non-functional ChromaDB store by
    returning an ``available: false`` payload with the error message.
    """
    import json as _json

    try:
        from academic_hunter.plugins.vector_stores import ChromaVectorStore

        store = ChromaVectorStore()
        collections = store.list_collections()
        collection_data = []
        total_papers = 0
        for coll_name in collections:
            stats = store.collection_stats(coll_name)
            total_papers += stats.get("count", 0)
            collection_data.append(stats)

        return _json.dumps(
            {
                "available": True,
                "collection_count": len(collections),
                "total_papers": total_papers,
                "collections": collection_data,
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as exc:
        return _json.dumps(
            {
                "available": False,
                "error": str(exc),
            },
            ensure_ascii=False,
            indent=2,
        )


async def _get_paper_resource(doi: str) -> str:
    """Return metadata (including abstract) for a paper identified by its DOI.

    Uses ``AcademicHunter.fetch_abstract_by_doi()`` under the hood.
    Returns a JSON payload with a ``found`` boolean.  If the paper cannot
    be retrieved the payload includes an ``error`` field.
    """
    import json as _json

    try:
        from academic_hunter import AcademicHunter

        hunter = AcademicHunter()
        abstract = hunter.fetch_abstract_by_doi(doi)
        if abstract:
            return _json.dumps(
                {
                    "doi": doi,
                    "found": True,
                    "abstract": abstract,
                },
                ensure_ascii=False,
                indent=2,
            )
        return _json.dumps(
            {
                "doi": doi,
                "found": False,
                "error": "No abstract found for this DOI",
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as exc:
        return _json.dumps(
            {
                "doi": doi,
                "found": False,
                "error": str(exc),
            },
            ensure_ascii=False,
            indent=2,
        )


# ── Prompt functions ──────────────────────────────────────────────────────────


async def _prompt_systematic_review(topic: str, research_question: str) -> str:
    """Template for a systematic literature review workflow.

    Guides the LLM through the Academic Hunter pipeline: configure search
    parameters, discover topic jargon, run the full pipeline, read the
    resulting report, and export findings to Obsidian.
    """
    return (
        "You are a systematic review assistant.\n"
        "\n"
        f"Topic: {topic}\n"
        f"Research Question: {research_question}\n"
        "\n"
        "Follow these steps:\n"
        "1. Use `update_config` to configure the search for this topic\n"
        "2. Run `quick_topic_discovery` to identify key jargon\n"
        "3. Use `run_search` to execute the pipeline\n"
        "4. Read the report with `read_latest_report`\n"
        "5. Export findings to Obsidian with `export_to_obsidian`\n"
    )


async def _prompt_quick_discovery(topic: str) -> str:
    """Template for a quick topic exploration.

    Instructs the LLM to discover papers via ``quick_topic_discovery``,
    search for conceptually similar work with ``semantic_search``, and
    persist results to Obsidian.
    """
    return (
        f"Explore the topic '{topic}' using Academic Hunter:\n"
        "\n"
        f"1. Use `quick_topic_discovery('{topic}')` to find relevant papers\n"
        "2. Use `semantic_search` to find conceptually similar work\n"
        "3. Export the findings to Obsidian\n"
    )


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
    mcp.tool()(search_europepmc)
    mcp.tool()(export_to_obsidian)

    # RAG tools
    mcp.tool()(semantic_search)
    mcp.tool()(index_papers)
    mcp.tool()(vector_store_stats)
    mcp.tool()(ask_papers)
    mcp.tool()(answer_question)

    # Europe PMC
    mcp.tool()(search_europepmc)

    # Analysis tools
    mcp.tool()(trending_topics)
    mcp.tool()(compare_papers)
    mcp.tool()(export_report)

    # Clustering tool
    mcp.tool()(cluster_papers)

    # Citation tools
    mcp.tool()(get_citation_count)
    mcp.tool()(get_citing_papers)
    mcp.tool()(find_novel_papers)
    mcp.tool()(find_related_papers)

    # ── Resources ───────────────────────────────────────────────────────────
    mcp.resource("academic-hunter://config/current")(_get_config_resource)
    mcp.resource("academic-hunter://reports/latest")(_get_latest_report_resource)
    mcp.resource("academic-hunter://vector-store/stats")(_get_vector_stats_resource)
    mcp.resource("academic-hunter://papers/{doi}")(_get_paper_resource)

    # ── Prompts ────────────────────────────────────────────────────────────
    mcp.prompt("systematic-review")(_prompt_systematic_review)
    mcp.prompt("quick-discovery")(_prompt_quick_discovery)

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
