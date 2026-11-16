"""Unit tests for the MCP server module.

Tests cover:
- ``create_mcp_server`` — instantiation and registration
- ``_discover_and_register`` — tool auto-discovery
- ``health_check`` — health endpoint
- ``run_mcp_server`` — argument parsing (excluding SSE mode start)
"""

import inspect
import logging
import re
from pathlib import Path
from unittest.mock import MagicMock, patch


def test_create_mcp_server_returns_fastmcp():
    """create_mcp_server returns a FastMCP instance."""
    from mcp.server.fastmcp import FastMCP

    from academic_hunter.interfaces.mcp.server import create_mcp_server

    server = create_mcp_server()
    assert isinstance(server, FastMCP)
    assert server.name == "academic-hunter"


def test_create_mcp_server_registers_tools(mock_ctx):
    """create_mcp_server triggers tool discovery and registration."""
    from academic_hunter.interfaces.mcp.server import create_mcp_server

    with patch("academic_hunter.interfaces.mcp.server._discover_and_register") as m_discover:
        server = create_mcp_server()
        m_discover.assert_called_once_with(server)


def test_create_mcp_server_resources_and_prompts(mock_ctx):
    """create_mcp_server creates a FastMCP with expected name."""
    from academic_hunter.interfaces.mcp.server import create_mcp_server

    server = create_mcp_server()
    assert server.name == "academic-hunter"
    assert hasattr(server, "name")
    assert hasattr(server, "tool")


def test_discover_and_register(mock_ctx):
    """_discover_and_register calls mcp.tool() for each discovered function.

    This is the discovered count, so it is one below the total the server
    exposes: `server_status` is registered by hand in ``server.py`` because it
    lives in ``interfaces/mcp/health.py``, outside the discovered package. A
    count that is one short is usually a tool that lost its `Context` annotation
    — auto-discovery then skips it without an import error — so bump this number
    only with the tool it accounts for.
    """
    from academic_hunter.interfaces.mcp.server import _discover_and_register

    mock_mcp = MagicMock()
    _discover_and_register(mock_mcp)

    assert mock_mcp.tool.call_count == 38


DOCUMENTED_TOOL_COUNTS = (
    ("README.md", r"\*\*(\d+) tools, 3 resources"),
    ("README.md", r"MCP Server \((\d+) tools"),
    ("docs/mcp_setup.md", r"the agent sees (\d+) tools"),
    ("docs/mcp_setup.md", r"the same (\d+) tools"),
)


def test_the_documented_tool_count_is_the_registered_one():
    """The docs said 44 while the code served 46, across two releases.

    The only other assertion on this number is in ``test_server_integration``,
    which is deselected by default — so the count a reader is told and the count
    an agent sees could drift apart with every suite green. This one counts the
    same way the server does, by driving the real discovery, and reads the
    numbers back out of the prose.
    """
    from academic_hunter.interfaces.mcp.server import _discover_and_register

    mock_mcp = MagicMock()
    _discover_and_register(mock_mcp)
    measured_discovered = mock_mcp.tool.call_count
    registered = measured_discovered + 1

    root = Path(__file__).resolve().parent.parent.parent.parent
    found = []
    for relative, pattern in DOCUMENTED_TOOL_COUNTS:
        text = (root / relative).read_text(encoding="utf-8")
        found += [(relative, int(number)) for number in re.findall(pattern, text)]

    assert len(found) == len(DOCUMENTED_TOOL_COUNTS), (
        f"a documented count is no longer where this test looks for it: "
        f"{[relative for relative, _ in found]}"
    )
    assert {number for _, number in found} == {registered}, (
        f"the code registers {measured_discovered} discovered tools plus the "
        f"hand-registered `server_status`, so a reader should be told "
        f"{registered}. The docs say {sorted({n for _, n in found})} — "
        f"update them, or say why the surface changed."
    )


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


async def test_the_collection_admin_tool_is_registered():
    """One collection per review leaves one collection per review behind, so the
    tool that removes one has to exist — and `delete_collection` takes `ctx` with
    a default, which is the annotation auto-discovery looks for."""
    from academic_hunter.interfaces.mcp.server import create_mcp_server

    server = create_mcp_server()
    names = {tool.name for tool in await server.list_tools()}

    assert {"vector_store_stats", "delete_collection"} <= names


def test_server_status_imported():
    """server_status tool is registered in the server module."""
    from academic_hunter.interfaces.mcp.server import _check_components, server_status

    assert callable(server_status)
    assert callable(_check_components)


async def test_a_tool_describes_the_default_it_actually_has():
    """The docstring *is* the description the agent reads to choose arguments.

    Four tools advertised a `top_k` default their signature did not have, so an
    agent asking for the documented amount of context silently got a different
    one. Nothing else checks that prose and signature agree.
    """
    import re

    from academic_hunter.interfaces.mcp.server import create_mcp_server

    server = create_mcp_server()
    tools = await server.list_tools()

    mismatched = []
    for tool in tools:
        properties = (tool.inputSchema or {}).get("properties", {})
        if "top_k" not in properties:
            continue
        stated = re.search(r"default\s+(\d+)", tool.description or "")
        actual = properties["top_k"].get("default")
        if stated and int(stated.group(1)) != actual:
            mismatched.append(f"{tool.name}: says {stated.group(1)}, has {actual}")

    assert not mismatched, mismatched


async def test_server_status_publishes_no_arguments():
    """The schema a client sees must not demand a `ctx` it cannot supply.

    `async def server_status(ctx)` without the `Context` annotation is published as
    a tool taking one required *string* named `ctx`, so every client call fails
    validation before the tool body runs. The mock-context test above passes
    either way, which is how this shipped.
    """
    from academic_hunter.interfaces.mcp.server import create_mcp_server

    server = create_mcp_server()
    tools = await server.list_tools()
    status = next(t for t in tools if t.name == "server_status")

    assert "ctx" not in status.inputSchema.get("properties", {})
    assert status.inputSchema.get("required", []) == []


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

        mock_server.run.assert_called_once()
        args, kwargs = mock_server.run.call_args
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

        m_get_logger.assert_any_call("academic_hunter")


async def test_the_server_publishes_instructions_naming_the_pipeline_in_order():
    """The one channel that reaches an agent before it picks a tool.

    A connected agent saw 43 tools and nothing saying a flow existed: the flow
    was written only in the MCP prompts, which a client delivers when the *user*
    invokes one. A fresh install therefore chose tools by name — measured, it
    left the pipeline at the first step and queried a single source directly.
    `instructions` is the field the protocol sends at connect, and it was unset.
    """
    from academic_hunter.interfaces.mcp.server import PIPELINE_TOOLS, create_mcp_server

    instructions = create_mcp_server().instructions

    assert instructions, "an agent learns the flow from here or not at all"
    assert len(instructions) <= 4096, (
        "Claude Code truncates server instructions past 4096 characters, so a "
        "step written after the cut is a step no agent is told about"
    )

    missing = [name for name in PIPELINE_TOOLS if name not in instructions]
    assert not missing, f"the flow names tools the instructions do not: {missing}"

    positions = [instructions.index(name) for name in PIPELINE_TOOLS]
    assert positions == sorted(positions), (
        f"the instructions name the steps out of order: {PIPELINE_TOOLS}"
    )


async def test_every_registered_tool_is_classified():
    """A tool the grouping does not know about is one the agent is not told about.

    Registration is by convention — a new `async def` with a `Context`
    parameter joins the surface by existing — so the grouping only stays true if
    something fails when a name is missing from it.
    """
    from academic_hunter.interfaces.mcp.server import (
        ON_DEMAND_SOURCES,
        PIPELINE_TOOLS,
        SUPPORT_TOOLS,
        create_mcp_server,
    )

    registered = {tool.name for tool in await create_mcp_server().list_tools()}
    declared = set(PIPELINE_TOOLS) | set(ON_DEMAND_SOURCES) | set(SUPPORT_TOOLS)

    assert registered == declared, (
        f"registered but undeclared: {sorted(registered - declared)}; "
        f"declared but not registered: {sorted(declared - registered)}"
    )


async def test_the_on_demand_tools_say_they_bypass_the_pipeline():
    """The description is what an agent reads at the moment it chooses a tool.

    A name alone never said which tools are the flow, and this server cannot see
    the request that would disambiguate them. With tool search on, only names
    load and this does not reach a first-party client — the marker is the
    closest thing to that moment that the server controls, not a guarantee.
    """
    from academic_hunter.interfaces.mcp.server import ON_DEMAND_SOURCES, create_mcp_server

    by_name = {tool.name: tool for tool in await create_mcp_server().list_tools()}

    silent = [
        name
        for name in ON_DEMAND_SOURCES
        if "bypass" not in (by_name[name].description or "").lower()
    ]

    assert not silent, f"these never say they bypass the pipeline: {silent}"
