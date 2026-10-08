"""Tests for the MCP exception hierarchy.

Validates that every exception subclass:
- Has the correct ``code`` attribute.
- Accepts optional ``details`` dict (defaults to empty).
- Is catchable via its base ``MCPToolError``.
"""

import pytest

from academic_hunter.interfaces.mcp.exceptions import (
    ConfigError,
    DiscoveryError,
    MCPToolError,
    ObsidianError,
    SearchError,
    VectorStoreError,
    WritingError,
)


class TestMCPToolError:
    """Base exception — every subclass extends this."""

    def test_default_code(self):
        err = MCPToolError("something broke")
        assert err.code == "TOOL_ERROR"

    def test_custom_code(self):
        err = MCPToolError("custom", code="CUSTOM_CODE")
        assert err.code == "CUSTOM_CODE"

    def test_details_defaults_to_empty_dict(self):
        err = MCPToolError("msg")
        assert err.details == {}

    def test_details_accepted(self):
        err = MCPToolError("msg", details={"key": "val"})
        assert err.details == {"key": "val"}

    def test_message_preserved(self):
        msg = "this is the error message"
        err = MCPToolError(msg)
        assert str(err) == msg

    def test_the_calculated_context_reaches_the_message(self):
        """FastMCP serialises ``str(exc)`` and drops the attributes.

        So a tool that worked out which directory it looked in was filling in a
        field the client never receives. The writing tools are the ones that do
        this: ``writing.py`` raises with ``details={"looked_in": …}`` on a missing
        run and ``details={"available": …}`` on an unknown section.
        """
        err = WritingError("Run not found", details={"looked_in": "/r/results"})

        assert "/r/results" in str(err)
        assert "WRITING_ERROR" in str(err)
        assert err.details == {"looked_in": "/r/results"}

    def test_every_detail_is_carried(self):
        err = MCPToolError("nope", code="CUSTOM", details={"a": 1, "b": "two"})

        assert "a=1" in str(err)
        assert "b=two" in str(err)
        assert "CUSTOM" in str(err)

    def test_an_error_without_details_keeps_its_message_verbatim(self):
        """The suffix is not decoration: it only appears when there is context."""
        assert str(MCPToolError("plain")) == "plain"
        assert str(WritingError("plain")) == "plain"


class TestConfigError:
    def test_code(self):
        err = ConfigError("config invalid")
        assert err.code == "CONFIG_ERROR"

    def test_is_mcp_tool_error(self):
        assert isinstance(ConfigError("x"), MCPToolError)


class TestSearchError:
    def test_code(self):
        err = SearchError("search failed")
        assert err.code == "SEARCH_ERROR"

    def test_is_mcp_tool_error(self):
        assert isinstance(SearchError("x"), MCPToolError)


class TestVectorStoreError:
    def test_code(self):
        err = VectorStoreError("vector store unreachable")
        assert err.code == "VECTOR_STORE_ERROR"

    def test_is_mcp_tool_error(self):
        assert isinstance(VectorStoreError("x"), MCPToolError)


class TestDiscoveryError:
    def test_code(self):
        err = DiscoveryError("API timeout")
        assert err.code == "DISCOVERY_ERROR"

    def test_is_mcp_tool_error(self):
        assert isinstance(DiscoveryError("x"), MCPToolError)


class TestObsidianError:
    def test_code(self):
        err = ObsidianError("vault not found")
        assert err.code == "OBSIDIAN_ERROR"

    def test_is_mcp_tool_error(self):
        assert isinstance(ObsidianError("x"), MCPToolError)


class TestCatchBase:
    """Ensure every subclass is catchable via ``except MCPToolError``."""

    @pytest.mark.parametrize(
        "exc_class",
        [ConfigError, SearchError, VectorStoreError, DiscoveryError, ObsidianError],
    )
    def test_catchable_as_base(self, exc_class):
        with pytest.raises(MCPToolError):
            raise exc_class("raised")
