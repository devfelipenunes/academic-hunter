"""MCP server for Academic Hunter — FastMCP instance, tool registration, and entry point."""

import logging

from mcp.server.fastmcp import Context, FastMCP
from starlette.responses import JSONResponse

from .tools.configuration import (
    read_config, update_config, list_config_history, restore_config_by_id,
)
from .tools.search import run_search, read_latest_report
from .tools.discovery import (
    fetch_paper_by_doi, explore_citation_graph,
    fetch_multiple_abstracts, quick_topic_discovery,
)
from .tools.europepmc import search_europepmc
from .tools.obsidian import export_to_obsidian
from .tools.trending import trending_topics
from .tools.comparison import compare_papers
from .tools.export import export_report
from .tools.novelty import find_novel_papers
from .tools.related import find_related_papers
from .tools.summarize import summarize_paper
from .tools.rag import (
    semantic_search, index_papers, vector_store_stats,
    ask_papers, answer_question, rerank_search,
)
from .tools.clustering import cluster_papers
from .tools.dedup import semantic_dedup
from .tools.citations import get_citation_count, get_citing_papers
from .tools.unpaywall import find_open_access
from .tools.lens import search_patents
from .tools.openaire import search_openaire
from .tools.biorxiv import search_biorxiv
from .tools.orcid import lookup_orcid
from .tools.datacite import search_datasets
from .tools.visualization import visualize_landscape, topic_evolution
from .exceptions import ConfigError, VectorStoreError
from .health import server_status, _check_components
from .resources import (
    get_config_resource, get_latest_report_resource,
    get_vector_stats_resource, get_paper_resource,
)
from .prompts import systematic_review, quick_discovery

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


async def health_check(request):
    """HTTP health-check endpoint for SSE mode.

    Reuses the same component checks as ``server_status``.
    """
    data = _check_components()
    del data["last_config_backup"]
    return JSONResponse(data)


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
    for fn in [
        server_status,
        run_search, read_latest_report,
        read_config, update_config, list_config_history, restore_config_by_id,
        fetch_paper_by_doi, explore_citation_graph, fetch_multiple_abstracts,
        quick_topic_discovery, search_europepmc, export_to_obsidian,
        semantic_search, rerank_search, index_papers,
        vector_store_stats, ask_papers, answer_question,
        trending_topics, compare_papers, export_report, summarize_paper,
        cluster_papers,
        get_citation_count, get_citing_papers,
        find_novel_papers, find_related_papers,
        semantic_dedup,
        visualize_landscape, topic_evolution,
        find_open_access, search_patents, search_openaire,
        search_biorxiv, lookup_orcid, search_datasets,
    ]:
        mcp.tool()(fn)

    # ── Resources ───────────────────────────────────────────────────────────
    mcp.resource("academic-hunter://config/current")(get_config_resource)
    mcp.resource("academic-hunter://reports/latest")(get_latest_report_resource)
    mcp.resource("academic-hunter://vector-store/stats")(get_vector_stats_resource)
    mcp.resource("academic-hunter://papers/{doi}")(get_paper_resource)

    # ── Prompts ────────────────────────────────────────────────────────────
    mcp.prompt("systematic-review")(systematic_review)
    mcp.prompt("quick-discovery")(quick_discovery)

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
        "-t", "--transport", choices=["stdio", "sse"],
        default=os.environ.get("ACADEMIC_MCP_TRANSPORT", "stdio"),
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--host", default=os.environ.get("ACADEMIC_MCP_HOST", "127.0.0.1"),
        help="Bind address for SSE mode (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port", type=int,
        default=int(os.environ.get("ACADEMIC_MCP_PORT", "8080")),
        help="Port for SSE mode (default: 8080)",
    )
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO)",
    )

    args = parser.parse_args()
    logging.getLogger("academic_hunter").setLevel(args.log_level.upper())

    server = create_mcp_server()

    if args.transport == "sse":
        logger.info("Starting MCP server in SSE mode on %s:%s", args.host, args.port)
        server.run(transport="sse", host=args.host, port=args.port)
    else:
        logger.info("Starting MCP server in stdio mode…")
        server.run()


if __name__ == "__main__":
    run_mcp_server()
