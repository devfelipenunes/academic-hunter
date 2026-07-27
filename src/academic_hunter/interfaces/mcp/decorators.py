"""Decorators for auto-registering MCP tools, resources, and prompts.

Usage::

    from .decorators import mcp_tool

    @mcp_tool()
    async def my_tool(ctx: Context, ...) -> str:
        ...

The ``_discover_and_register()`` function in ``server.py`` uses the
``__mcp_tool__`` marker attribute on functions, but also falls back to
signature-based detection (async functions whose parameters include a
``Context``-typed parameter) for modules that do not use the decorator.
"""

_TOOL_REGISTRY: list = []
_RESOURCE_REGISTRY: list = []
_PROMPT_REGISTRY: list = []


def mcp_tool(name: str | None = None):
    """Decorator that marks a function as an MCP tool for auto-registration.

    Args:
        name: Optional explicit tool name.  Defaults to ``func.__name__``.

    The decorated function is appended to the global ``_TOOL_REGISTRY``
    and given a ``__mcp_tool__ = True`` attribute so that
    :func:`_discover_and_register` can find it.
    """
    def decorator(func):
        func.__mcp_tool__ = True
        func.__mcp_tool_name__ = name or func.__name__
        _TOOL_REGISTRY.append(func)
        return func
    return decorator


def get_tool_registry():
    """Return a copy of the current tool registry."""
    return list(_TOOL_REGISTRY)
