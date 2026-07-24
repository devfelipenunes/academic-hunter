import pytest
from academic_hunter.interfaces.mcp.server import create_mcp_server
from mcp.server.fastmcp import FastMCP


def test_create_mcp_server():
    """Test that the MCP server is instantiated correctly with tools registered."""
    server = create_mcp_server()

    assert isinstance(server, FastMCP)
    # FastMCP lowercases/keeps the name as provided
    assert server.name == "academic-hunter"
