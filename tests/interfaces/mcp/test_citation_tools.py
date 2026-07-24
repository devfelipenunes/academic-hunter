"""Tests for citation analysis MCP tools (OpenCitations/COCI)."""

import pytest
from unittest.mock import patch, MagicMock
from academic_hunter.interfaces.mcp.tools.citations import (
    get_citation_count,
    get_citing_papers,
)
from academic_hunter.interfaces.mcp.exceptions import MCPToolError


async def test_get_citation_count(mock_ctx):
    """Returns citation count for a DOI."""
    mock_response = [{"count": "3"}]

    with patch("academic_hunter.interfaces.mcp.tools.citations.requests.get") as m_get:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = mock_response
        m_get.return_value = resp
        result = await get_citation_count(mock_ctx, "10.1234/test")
        assert "3" in result
        assert "citations" in result.lower()
        mock_ctx.info.assert_called()


async def test_get_citation_count_zero(mock_ctx):
    """Returns zero when no citations found."""
    with patch("academic_hunter.interfaces.mcp.tools.citations.requests.get") as m_get:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = [{"count": "0"}]
        m_get.return_value = resp
        result = await get_citation_count(mock_ctx, "10.1234/unknown")
        assert "0" in result


async def test_get_citation_count_error(mock_ctx):
    """Handles API errors gracefully."""
    with patch("academic_hunter.interfaces.mcp.tools.citations.requests.get") as m_get:
        m_get.side_effect = Exception("API unavailable")
        with pytest.raises(MCPToolError):
            await get_citation_count(mock_ctx, "10.1234/test")
        mock_ctx.error.assert_called()


async def test_get_citing_papers(mock_ctx):
    """Returns citing papers with details."""
    mock_data = [{"citing": "10.1000/c1", "creation": "2024-01-15", "timespan": "P1Y"}]
    with patch("academic_hunter.interfaces.mcp.tools.citations.requests.get") as m_get:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = mock_data
        m_get.return_value = resp
        result = await get_citing_papers(mock_ctx, "10.1234/test", limit=5)
        assert "10.1000/c1" in result
        mock_ctx.info.assert_called()
