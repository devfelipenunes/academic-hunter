"""Tests for Unpaywall tool."""

from unittest.mock import MagicMock, patch

import pytest

from academic_hunter.interfaces.mcp.exceptions import MCPToolError
from academic_hunter.interfaces.mcp.tools.unpaywall import find_open_access


async def test_find_open_access_oa(mock_ctx):
    """Returns OA status for an open-access paper."""
    mock_response = {
        "is_oa": True,
        "oa_status": "gold",
        "best_oa_location": {
            "url_for_pdf": "https://example.com/paper.pdf",
            "host_type": "publisher",
            "license": "cc-by",
            "version": "publishedVersion",
        },
    }
    with patch("academic_hunter.interfaces.mcp.tools.unpaywall.requests.get") as m_get:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = mock_response
        m_get.return_value = resp
        result = await find_open_access(mock_ctx, "10.1234/test", "test@example.com")
        assert "✅ Yes" in result
        assert "https://example.com/paper.pdf" in result
        mock_ctx.info.assert_called()


async def test_find_open_access_closed(mock_ctx):
    """Returns OA status for a closed-access paper."""
    with patch("academic_hunter.interfaces.mcp.tools.unpaywall.requests.get") as m_get:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"is_oa": False, "oa_status": "closed"}
        m_get.return_value = resp
        result = await find_open_access(mock_ctx, "10.1234/paywalled")
        assert "❌ No" in result


async def test_find_open_access_error(mock_ctx):
    """Handles API errors gracefully."""
    with patch("academic_hunter.interfaces.mcp.tools.unpaywall.requests.get") as m_get:
        m_get.side_effect = Exception("API error")
        with pytest.raises(MCPToolError):
            await find_open_access(mock_ctx, "10.1234/test")
        mock_ctx.error.assert_called()
