"""Tests for bioRxiv/medRxiv search tool."""

import pytest
from unittest.mock import patch, MagicMock
from academic_hunter.interfaces.mcp.tools.biorxiv import search_biorxiv
from academic_hunter.interfaces.mcp.exceptions import MCPToolError


async def test_search_biorxiv(mock_ctx):
    """Returns preprint search results."""
    mock_collection = [
        {
            "title": "Deep Learning in Genomic Medicine",
            "authors": "Smith J, Doe A",
            "doi": "10.1101/2024.01.15.123456",
            "date": "2024-01-15",
            "category": "bioinformatics",
            "abstract": "This paper applies deep learning to genomic data analysis.",
        }
    ]
    with patch("academic_hunter.interfaces.mcp.tools.biorxiv.requests.get") as m_get:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"collection": mock_collection}
        m_get.return_value = resp
        result = await search_biorxiv(mock_ctx, "deep learning", server="bio", limit=5)
        assert "Deep Learning in Genomic Medicine" in result
        assert "bioRxiv" in result
        assert "10.1101" in result
        mock_ctx.info.assert_called()


async def test_search_medrxiv(mock_ctx):
    """Searches medRxiv."""
    mock_collection = [
        {
            "title": "COVID-19 Vaccine Efficacy",
            "authors": "Lee K",
            "doi": "10.1101/2024.03.01.567890",
            "date": "2024-03-01",
            "category": "epidemiology",
            "abstract": "Clinical trial results for COVID-19 vaccine.",
        }
    ]
    with patch("academic_hunter.interfaces.mcp.tools.biorxiv.requests.get") as m_get:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"collection": mock_collection}
        m_get.return_value = resp
        result = await search_biorxiv(mock_ctx, "COVID-19", server="med", limit=5)
        assert "COVID-19 Vaccine Efficacy" in result
        assert "medRxiv" in result


async def test_search_biorxiv_no_results(mock_ctx):
    """Graceful when no matching preprints."""
    mock_collection = [
        {"title": "Unrelated Paper", "abstract": "About something else entirely"}
    ]
    with patch("academic_hunter.interfaces.mcp.tools.biorxiv.requests.get") as m_get:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"collection": mock_collection}
        m_get.return_value = resp
        result = await search_biorxiv(mock_ctx, "nonexistent", server="bio", limit=5)
        assert "No matching preprints" in result


async def test_search_biorxiv_empty_collection(mock_ctx):
    """Graceful when API returns empty collection."""
    with patch("academic_hunter.interfaces.mcp.tools.biorxiv.requests.get") as m_get:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"collection": []}
        m_get.return_value = resp
        result = await search_biorxiv(mock_ctx, "anything", server="bio", limit=5)
        assert "No preprints found" in result


async def test_search_biorxiv_invalid_server(mock_ctx):
    """Validates server parameter."""
    result = await search_biorxiv(mock_ctx, "test", server="invalid")
    assert "must be 'bio' or 'med'" in result


async def test_search_biorxiv_error(mock_ctx):
    """Handles API errors."""
    with patch("academic_hunter.interfaces.mcp.tools.biorxiv.requests.get") as m_get:
        m_get.side_effect = Exception("API error")
        with pytest.raises(MCPToolError):
            await search_biorxiv(mock_ctx, "test", server="bio")
        mock_ctx.error.assert_called()
