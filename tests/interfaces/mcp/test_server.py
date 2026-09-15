"""Unit tests for the MCP server module.

Tests cover:
- ``create_mcp_server`` — instantiation and registration
- ``_discover_and_register`` — tool auto-discovery
- ``health_check`` — health endpoint
- ``run_mcp_server`` — argument parsing (excluding SSE mode start)
"""

import inspect
import logging
from unittest.mock import patch, MagicMock, PropertyMock


def test_create_mcp_server_returns_fastmcp():
    """create_mcp_server returns a FastMCP instance."""
    from academic_hunter.interfaces.mcp.server import create_mcp_server
    from mcp.server.fastmcp import FastMCP

    server = create_mcp_server()
    assert isinstance(server, FastMCP)
    assert server.name == "academic-hunter"


def test_create_mcp_server_registers_tools(mock_ctx):
    """create_mcp_server triggers tool discovery and registration."""
    from academic_hunter.interfaces.mcp.server import create_mcp_server

    with patch("academic_hunter.interfaces.mcp.server._discover_and_register") as m_discover:
        server = create_mcp_server()
        m_discover.assert_called_once()


def test_create_mcp_server_resources_and_prompts(mock_ctx):
    """create_mcp_server creates a FastMCP with expected name."""
    from academic_hunter.interfaces.mcp.server import create_mcp_server

    server = create_mcp_server()
    assert server.name == "academic-hunter"
    # The server has the expected attributes from FastMCP
    assert hasattr(server, "name")
    assert hasattr(server, "tool")


def test_discover_and_register(mock_ctx):
    """_discover_and_register calls mcp.tool() for each discovered function."""
    from academic_hunter.interfaces.mcp.server import _discover_and_register

    mock_mcp = MagicMock()
    _discover_and_register(mock_mcp)

    # Should have called mcp.tool() multiple times (one per tool module function)
    assert mock_mcp.tool.call_count >= 10


async def test_the_fulltext_tools_are_registered():
    """Registration is by convention, so it can fail without failing anything.

    Auto-discovery picks up an `async def` only if one of its parameters is
    annotated `Context`; a tool that loses that annotation stops existing with no
    import error and no red test. Two tools have already shipped dead in this
    project for exactly that reason.
    """
    from academic_hunter.interfaces.mcp.server import create_mcp_server

    server = create_mcp_server()
    names = {tool.name for tool in await server.list_tools()}

    assert {"fulltext_status", "index_fulltext", "chunk_search"} <= names


def test_server_status_imported():
    """server_status tool is registered in the server module."""
    from academic_hunter.interfaces.mcp.server import server_status, _check_components

    assert callable(server_status)
    assert callable(_check_components)


async def test_health_check(mock_ctx):
    """Health check endpoint returns component status."""
    from academic_hunter.interfaces.mcp.server import health_check

    with patch("academic_hunter.interfaces.mcp.server._check_components") as m_check:
        m_check.return_value = {
            "status": "ok", "server": "academic-hunter",
            "config_loaded": True,
            "vector_store": {"available": True, "paper_count": 5},
            "last_config_backup": "2025-01-01",
        }
        from starlette.requests import Request
        mock_request = MagicMock(spec=Request)
        response = await health_check(mock_request)

    assert response.status_code == 200
    assert "academic-hunter" in str(response.body)


def test_setup_logging(mock_ctx):
    """_setup_logging configures log levels for noisy libraries."""
    from academic_hunter.interfaces.mcp.server import _setup_logging

    # Reset loggers first
    for name in ("chromadb", "urllib3", "httpx"):
        logging.getLogger(name).setLevel(logging.NOTSET)

    _setup_logging()

    assert logging.getLogger("chromadb").level == logging.WARNING
    assert logging.getLogger("urllib3").level == logging.WARNING
    assert logging.getLogger("httpx").level == logging.WARNING


def test_run_mcp_server_parses_stdio():
    """run_mcp_server parses arguments and starts in stdio mode."""
    from academic_hunter.interfaces.mcp.server import run_mcp_server

    with patch("sys.argv", ["academic-mcp"]), \
         patch("academic_hunter.interfaces.mcp.server.create_mcp_server") as m_create, \
         patch.object(logging.getLogger("academic_hunter"), "setLevel"):

        mock_server = MagicMock()
        m_create.return_value = mock_server

        run_mcp_server()

        # Should run in stdio mode by default
        mock_server.run.assert_called_once()
        args, kwargs = mock_server.run.call_args
        # No transport argument means stdio (the default)
        assert kwargs.get("transport") is None or kwargs.get("host") is None


def _accepted_run_kwargs() -> set:
    """The keyword arguments the installed `FastMCP.run` really accepts.

    A bare `MagicMock` accepts anything, which is how this call shipped passing
    `host=` and `port=` to a method that takes neither — the test asserted the
    invalid call and so pinned the bug in place. Checking against the real
    signature is what stops that from happening again.
    """
    from mcp.server.fastmcp import FastMCP

    return set(inspect.signature(FastMCP.run).parameters) - {"self"}


def test_run_mcp_server_parses_sse():
    """run_mcp_server parses arguments and starts in SSE mode."""
    from academic_hunter.interfaces.mcp.server import run_mcp_server

    with patch("sys.argv", ["academic-mcp", "-t", "sse", "--port", "9999"]), \
         patch("academic_hunter.interfaces.mcp.server.create_mcp_server") as m_create, \
         patch.object(logging.getLogger("academic_hunter"), "setLevel"):

        mock_server = MagicMock()
        m_create.return_value = mock_server

        run_mcp_server()

        m_create.assert_called_once_with(host="127.0.0.1", port=9999)
        mock_server.run.assert_called_once_with(transport="sse")

        unknown = set(mock_server.run.call_args.kwargs) - _accepted_run_kwargs()
        assert not unknown, f"FastMCP.run does not accept {unknown}"


def test_run_mcp_server_parses_env_vars():
    """run_mcp_server reads transport from environment variable."""
    from academic_hunter.interfaces.mcp.server import run_mcp_server

    with patch("sys.argv", ["academic-mcp"]), \
         patch.dict("os.environ", {"ACADEMIC_MCP_TRANSPORT": "sse", "ACADEMIC_MCP_PORT": "7777"}), \
         patch("academic_hunter.interfaces.mcp.server.create_mcp_server") as m_create, \
         patch.object(logging.getLogger("academic_hunter"), "setLevel"):

        mock_server = MagicMock()
        m_create.return_value = mock_server

        run_mcp_server()

        m_create.assert_called_once_with(host="127.0.0.1", port=7777)
        mock_server.run.assert_called_once_with(transport="sse")


def test_run_mcp_server_debug_log_level():
    """run_mcp_server respects --log-level DEBUG."""
    from academic_hunter.interfaces.mcp.server import run_mcp_server

    with patch("sys.argv", ["academic-mcp", "--log-level", "DEBUG"]), \
         patch("academic_hunter.interfaces.mcp.server.create_mcp_server"), \
         patch("logging.getLogger") as m_get_logger:

        run_mcp_server()

        # Should set academic_hunter logger to DEBUG
        m_get_logger.assert_any_call("academic_hunter")
