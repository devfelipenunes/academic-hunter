"""Tests for MCP auto-registration decorators.

Verifies that:
- ``@mcp_tool()`` marks functions correctly.
- ``get_tool_registry()`` returns the registered functions.
- Registry content reflects the marker attributes.
"""

from academic_hunter.interfaces.mcp.decorators import mcp_tool, get_tool_registry


def test_mcp_tool_marks_function():
    """@mcp_tool marks the function with __mcp_tool__ attribute."""
    @mcp_tool()
    async def my_tool():
        pass

    assert hasattr(my_tool, "__mcp_tool__")
    assert my_tool.__mcp_tool__ is True
    assert hasattr(my_tool, "__mcp_tool_name__")
    assert my_tool.__mcp_tool_name__ == "my_tool"


def test_mcp_tool_custom_name():
    """@mcp_tool(name="custom_name") uses the provided name."""
    @mcp_tool(name="custom_name")
    async def some_func():
        pass

    assert some_func.__mcp_tool_name__ == "custom_name"


def test_get_tool_registry_includes_decorated():
    """get_tool_registry includes functions decorated with @mcp_tool."""
    # Reset global state: pop our test entries
    # Each call appends to _TOOL_REGISTRY
    registry_before = len(get_tool_registry())

    @mcp_tool()
    async def my_registered_tool():
        return "ok"

    registry = get_tool_registry()
    assert my_registered_tool in registry
    assert len(registry) == registry_before + 1


def test_get_tool_registry_returns_copy():
    """get_tool_registry returns a list copy, not the original."""
    registry = get_tool_registry()
    # Modifying the returned list should not affect the internal registry
    registry.clear()
    assert len(get_tool_registry()) > 0


def test_multiple_tools_registered():
    """Multiple decorated functions are all in the registry."""
    before = len(get_tool_registry())

    @mcp_tool()
    async def tool_a(): pass

    @mcp_tool()
    async def tool_b(): pass

    @mcp_tool(name="tool_c")
    async def other(): pass

    assert len(get_tool_registry()) == before + 3


def test_mcp_tool_non_async():
    """@mcp_tool also works on synchronous functions."""
    @mcp_tool()
    def sync_tool():
        return "sync"

    assert hasattr(sync_tool, "__mcp_tool__")
    assert sync_tool.__mcp_tool__ is True
    assert sync_tool.__mcp_tool_name__ == "sync_tool"
