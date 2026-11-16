"""MCP server for Academic Hunter — FastMCP instance, tool registration, and entry point.

Tools are auto-discovered from the ``tools/`` package so that adding a new
tool module does **not** require editing this file — just create an ``async``
function with a ``ctx: Context`` parameter.
"""

import importlib
import inspect
import logging
from pathlib import Path

from starlette.responses import JSONResponse

from academic_hunter.core.infra import paths
from mcp.server.fastmcp import Context, FastMCP

from .health import _check_components, server_status
from .prompts import quick_discovery, systematic_review
from .resources import (
    get_config_resource,
    get_latest_report_resource,
    get_paper_resource,
    get_vector_stats_resource,
)

logger = logging.getLogger("academic_hunter.mcp")

PIPELINE_TOOLS = (
    "quick_topic_discovery",
    "update_config",
    "run_search",
    "read_latest_report",
)

ON_DEMAND_SOURCES = (
    "search_source",
    "find_open_access",
    "lookup_orcid",
    "get_citation_count",
    "get_citing_papers",
    "fetch_paper_by_doi",
    "fetch_multiple_abstracts",
    "explore_citation_graph",
)

SUPPORT_TOOLS = (
    "cluster_papers",
    "find_novel_papers",
    "semantic_search",
    "rerank_search",
    "answer_question",
    "semantic_dedup",
    "find_related_papers",
    "trending_topics",
    "topic_evolution",
    "chunk_search",
    "index_fulltext",
    "index_papers",
    "compare_papers",
    "summarize_paper",
    "export_report",
    "outline_paper",
    "paper_context",
    "verify_citations",
    "verify_numbers",
    "export_to_obsidian",
    "read_config",
    "list_config_history",
    "restore_config_by_id",
    "server_status",
    "fulltext_status",
    "vector_store_stats",
    "delete_collection",
)

SERVER_INSTRUCTIONS = """\
Academic Hunter runs a literature-review pipeline. When the user asks to
research, review or find the literature on a topic, run that pipeline; do not
reach for a single-source tool instead.

The pipeline, in this order:

1. quick_topic_discovery — the terms the field's own titles use, counted, with
   sample titles. It returns no anchors, no categories and no weights: it is
   evidence, not a configuration. You write the configuration from those terms.
2. update_config — applies the anchors and technical terms you wrote. Its reply
   states what the configuration will do and what it will fail to do; read the
   second part before searching.
3. run_search — runs the pipeline. It refuses a configuration with no anchors.
   Read the coverage it reports: a source listed as never queried was never
   asked, which is a defect in the configuration and not an empty result.
4. read_latest_report — reads the consolidated report of that run.

These tools query one external source directly and bypass the pipeline, so they
produce no run and no report: search_source — which takes the source as an
argument, and reaches OpenAIRE, DataCite and Lens.org — plus find_open_access,
lookup_orcid, get_citation_count,
get_citing_papers, fetch_paper_by_doi, fetch_multiple_abstracts and
explore_citation_graph. Reach for one only when the user asks for something
specific — a DOI, a patent, a dataset, a preprint, one source by name.
"""


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
    data = await _check_components()
    del data["last_config_backup"]
    return JSONResponse(data)


def _discover_and_register(mcp: FastMCP) -> None:
    """Auto-discover all tool functions from the ``tools/`` package.

    Any ``async def`` function whose **type-annotated** parameters include
    ``Context`` (from ``mcp.server.fastmcp``) is automatically registered as
    an MCP tool via ``mcp.tool()``.

    Private modules (``_*.py``) and ``__init__.py`` are skipped.  Helper
    functions without a ``Context``-typed parameter are ignored.
    """
    tools_dir = Path(__file__).resolve().parent / "tools"
    for f in sorted(tools_dir.glob("*.py")):
        if f.name.startswith("_") or f.name == "__init__.py":
            continue
        module_name = f.stem
        module = importlib.import_module(
            f".tools.{module_name}", "academic_hunter.interfaces.mcp"
        )
        for attr_name in dir(module):
            func = getattr(module, attr_name)
            if not inspect.iscoroutinefunction(func):
                continue
            sig = inspect.signature(func)
            has_ctx = any(
                p.annotation is Context
                for p in sig.parameters.values()
            )
            if not has_ctx:
                continue
            logger.debug("Auto-registering tool: %s (from %s)", func.__name__, module_name)
            mcp.tool()(func)


def create_mcp_server(host: str = "127.0.0.1", port: int = 8000) -> FastMCP:
    """Instantiate the FastMCP server and register all tools, resources, and prompts."""
    _setup_logging()
    logger.info("Creating Academic Hunter MCP server…")

    mcp = FastMCP(
        "academic-hunter",
        instructions=SERVER_INSTRUCTIONS,
        host=host,
        port=port,
        dependencies=["requests", "pandas", "chromadb"],
    )

    _discover_and_register(mcp)

    mcp.tool()(server_status)

    mcp.resource("academic-hunter://config/current")(get_config_resource)
    mcp.resource("academic-hunter://reports/latest")(get_latest_report_resource)
    mcp.resource("academic-hunter://vector-store/stats")(get_vector_stats_resource)
    mcp.resource("academic-hunter://papers/{doi}")(get_paper_resource)

    mcp.prompt("systematic-review")(systematic_review)
    mcp.prompt("quick-discovery")(quick_discovery)

    mcp.custom_route("/health", methods=["GET"])(health_check)

    return mcp


def _report_resolution() -> None:
    """Name the config and data location this process resolved to.

    Both are chosen by a search order that depends on the environment the client
    spawned the server in, so "which config am I actually reading" is not
    something the operator can see. It is logged rather than silent for the same
    reason the packaged default carries a warning: a run against an empty
    config finds nothing, and nothing about that looks like a missing file.
    """
    try:
        config = paths.resolve_config_path()
    except Exception as exc:
        logger.error("No usable configuration: %s", exc)
    else:
        if config.is_default:
            logger.warning(
                "No configuration was found, so the packaged default at %s is in "
                "use. It has no anchors and no technical weights, so searches "
                "will score nothing until you set them with update_config, write "
                "%s, or point %s at your own file.",
                config.path, paths.user_config_file(), paths.CONFIG_ENV,
            )
        else:
            logger.info("Config: %s (chosen by: %s)", config.path, config.origin)

    try:
        location = paths.resolve_location()
    except Exception as exc:
        logger.error("No usable data directory: %s", exc)
    else:
        logger.info(
            "Data: %s (chosen by: %s); runs go to %s",
            location.data_dir, location.origin, location.results_dir,
        )


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
    parser.add_argument(
        "--config", default=None, metavar="PATH",
        help="Config file to read. Overrides ACADEMIC_HUNTER_CONFIG and the "
             "search order, which is: that variable, ./config.json, "
             "$CLAUDE_PROJECT_DIR/config.json, "
             "$XDG_CONFIG_HOME/academic-hunter/config.json, the packaged default.",
    )
    parser.add_argument(
        "--data-dir", default=None, metavar="PATH",
        help="The project directory: runs go to PATH/results, and the vector "
             "store and config history to PATH/.academic_hunter. Overrides "
             "ACADEMIC_HUNTER_DATA_DIR and the search order, which is: that "
             "variable, $CLAUDE_PROJECT_DIR, the current directory when it holds "
             ".academic_hunter or config.json, the checkout, then "
             "$XDG_DATA_HOME/academic-hunter.",
    )

    args = parser.parse_args()
    logging.getLogger("academic_hunter").setLevel(args.log_level.upper())

    if args.config:
        os.environ[paths.CONFIG_ENV] = str(Path(args.config).expanduser().resolve())
    if args.data_dir:
        os.environ[paths.DATA_ENV] = str(Path(args.data_dir).expanduser().resolve())

    _setup_logging()
    _report_resolution()

    server = create_mcp_server(host=args.host, port=args.port)

    if args.transport == "sse":
        logger.info("Starting MCP server in SSE mode on %s:%s", args.host, args.port)
        server.run(transport="sse")
    else:
        logger.info("Starting MCP server in stdio mode…")
        server.run()


if __name__ == "__main__":
    run_mcp_server()
