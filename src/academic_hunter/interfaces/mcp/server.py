"""MCP server for Academic Hunter — FastMCP instance, tool registration, and entry point.

Tools are auto-discovered from the ``tools/`` package so that adding a new
tool module does **not** require editing this file — just create an ``async``
function with a ``ctx: Context`` parameter.
"""

import importlib
import inspect
import logging
from pathlib import Path

from mcp.server.fastmcp import Context, FastMCP
from starlette.responses import JSONResponse

from .health import server_status, _check_components
from .resources import (
    get_config_resource, get_latest_report_resource,
    get_vector_stats_resource, get_paper_resource,
)
from .prompts import systematic_review, quick_discovery
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


async def health_check(request):
    """HTTP health-check endpoint for SSE mode.

    Reuses the same component checks as ``server_status``.
    """
    data = await _check_components()
    del data["last_config_backup"]
    return JSONResponse(data)


# ── Auto-discovery helpers ────────────────────────────────────────────────────


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


# ── Server factory ────────────────────────────────────────────────────────────


def create_mcp_server() -> FastMCP:
    """Instantiate the FastMCP server and register all tools, resources, and prompts."""
    _setup_logging()
    logger.info("Creating Academic Hunter MCP server…")

    mcp = FastMCP(
        "academic-hunter",
        dependencies=["requests", "pandas", "bibtexparser", "chromadb"],
    )

    # ── Tools (auto-discovered from tools/ package) ─────────────────────────
    _discover_and_register(mcp)

    # Tools outside the tools/ package (registered manually)
    mcp.tool()(server_status)

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
