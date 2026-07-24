"""Tests for Lens.org patent search tool."""

from unittest.mock import MagicMock, patch

import pytest

from academic_hunter.interfaces.mcp.tools.lens import search_patents


async def test_search_patents(mock_ctx):
    """Returns patent search results."""
    mock_response = {
        "data": [
            {
                "title": "Blockchain Consensus Method",
                "inventor": ["Alice Smith", "Bob Jones"],
                "publicationYear": 2023,
            },
            {
                "title": "Patent on Distributed Ledger",
                "inventor": ["Carol Lee"],
                "publicationYear": 2022,
            },
        ]
    }
    with patch("academic_hunter.interfaces.mcp.tools.lens.requests.post") as m_post:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = mock_response
        m_post.return_value = resp
        result = await search_patents(mock_ctx, "blockchain", limit=5)
        assert "Blockchain Consensus Method" in result
        assert "Alice Smith" in result
        mock_ctx.info.assert_called()


async def test_search_patents_no_results(mock_ctx):
    """Graceful when no results."""
    with patch("academic_hunter.interfaces.mcp.tools.lens.requests.post") as m_post:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"data": []}
        m_post.return_value = resp
        result = await search_patents(mock_ctx, "zzzzzznothing")
        assert "No patents found" in result
