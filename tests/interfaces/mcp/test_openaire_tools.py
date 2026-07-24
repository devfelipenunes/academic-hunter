"""Tests for OpenAIRE search tool."""

import pytest
from unittest.mock import patch, MagicMock
from academic_hunter.interfaces.mcp.tools.openaire import search_openaire
from academic_hunter.interfaces.mcp.exceptions import MCPToolError


async def test_search_openaire(mock_ctx):
    """Returns search results with funding info."""
    mock_response = {
        "response": {
            "results": [
                {
                    "metadata": {
                        "title": "Blockchain for Healthcare",
                        "creator": ["Alice Smith", "Bob Jones"],
                        "publicationDate": "2024-03-15",
                        "pid": "10.1000/test",
                        "isOpenAccess": True,
                        "fundingReference": [{"funderName": "European Commission"}],
                    }
                }
            ]
        }
    }
    with patch("academic_hunter.interfaces.mcp.tools.openaire.requests.get") as m_get:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = mock_response
        m_get.return_value = resp
        result = await search_openaire(mock_ctx, "blockchain healthcare", limit=5)
        assert "Blockchain for Healthcare" in result
        assert "✅ OA" in result
        assert "European Commission" in result
        mock_ctx.info.assert_called()


async def test_search_openaire_no_results(mock_ctx):
    """Graceful when no results."""
    with patch("academic_hunter.interfaces.mcp.tools.openaire.requests.get") as m_get:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"response": {"results": []}}
        m_get.return_value = resp
        result = await search_openaire(mock_ctx, "zzzzznothing")
        assert "No results found" in result


async def test_search_openaire_error(mock_ctx):
    """Handles API errors gracefully."""
    with patch("academic_hunter.interfaces.mcp.tools.openaire.requests.get") as m_get:
        m_get.side_effect = Exception("API error")
        with pytest.raises(MCPToolError):
            await search_openaire(mock_ctx, "test")
        mock_ctx.error.assert_called()
