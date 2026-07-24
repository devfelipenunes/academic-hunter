"""Tests for DataCite search tool."""

from unittest.mock import MagicMock, patch

import pytest

from academic_hunter.interfaces.mcp.exceptions import MCPToolError
from academic_hunter.interfaces.mcp.tools.datacite import search_datasets


async def test_search_datasets(mock_ctx):
    """Returns dataset search results."""
    mock_response = {
        "data": [
            {
                "attributes": {
                    "titles": [{"title": "Genomic Dataset for Cancer Research"}],
                    "creators": [{"name": "Smith, J"}, {"name": "Doe, A"}],
                    "publicationYear": 2024,
                    "doi": "10.5281/zenodo.12345",
                    "resourceTypeGeneral": "Dataset",
                    "publisher": "Zenodo",
                    "relatedIdentifiers": [{"relationType": "IsCitedBy"}],
                }
            }
        ]
    }

    with patch("academic_hunter.interfaces.mcp.tools.datacite.requests.get") as m_get:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = mock_response
        m_get.return_value = resp
        result = await search_datasets(mock_ctx, "cancer genomics", limit=5, resource_type="dataset")
        assert "Genomic Dataset" in result
        assert "Dataset" in result
        assert "10.5281" in result
        assert "Zenodo" in result
        mock_ctx.info.assert_called()


async def test_search_datasets_no_results(mock_ctx):
    """Graceful when no results."""
    with patch("academic_hunter.interfaces.mcp.tools.datacite.requests.get") as m_get:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"data": []}
        m_get.return_value = resp
        result = await search_datasets(mock_ctx, "zzzzznothing")
        assert "No results" in result


async def test_search_datasets_error(mock_ctx):
    """Handles API errors."""
    with patch("academic_hunter.interfaces.mcp.tools.datacite.requests.get") as m_get:
        m_get.side_effect = Exception("API error")
        with pytest.raises(MCPToolError):
            await search_datasets(mock_ctx, "test")
        mock_ctx.error.assert_called()
