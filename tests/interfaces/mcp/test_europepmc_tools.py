"""Tests for Europe PMC search tool."""

import pytest
from unittest.mock import patch, MagicMock
from academic_hunter.interfaces.mcp.tools.europepmc import search_europepmc
from academic_hunter.interfaces.mcp.exceptions import MCPToolError


async def test_search_europepmc_success(mock_ctx):
    """Returns formatted search results from Europe PMC."""
    mock_response = {
        "hitCount": 42,
        "resultList": {
            "result": [
                {
                    "title": "Deep Learning in Biology",
                    "authorString": "Smith J, Doe A",
                    "firstPublicationDate": "2024-03-15",
                    "doi": "10.1000/test",
                    "source": "Nature",
                    "isOpenAccess": True,
                    "abstractText": "This paper explores deep learning for genomic analysis.",
                },
                {
                    "title": "CRISPR Applications",
                    "authorString": "Lee K, Wang B",
                    "firstPublicationDate": "2023-11-01",
                    "doi": "10.1000/crispr",
                    "source": "Science (preprint)",
                    "isOpenAccess": False,
                    "abstractText": "Novel CRISPR applications in gene therapy.",
                },
            ]
        },
    }

    with patch("academic_hunter.interfaces.mcp.tools.europepmc.requests.get") as m_get:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = mock_response
        m_get.return_value = resp

        result = await search_europepmc(mock_ctx, "deep learning", limit=10)

        assert "Deep Learning in Biology" in result
        assert "CRISPR Applications" in result
        assert "[OA]" in result
        assert "Europe PMC" in result or "Results" in result
        mock_ctx.info.assert_called()


async def test_search_europepmc_no_results(mock_ctx):
    """Graceful handling when no results."""
    mock_response = {"hitCount": 0, "resultList": {"result": []}}

    with patch("academic_hunter.interfaces.mcp.tools.europepmc.requests.get") as m_get:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = mock_response
        m_get.return_value = resp

        result = await search_europepmc(mock_ctx, "zzzznothingxxx")
        assert "No results found" in result


async def test_search_europepmc_error(mock_ctx):
    """Handles API errors gracefully."""
    with patch("academic_hunter.interfaces.mcp.tools.europepmc.requests.get") as m_get:
        m_get.side_effect = Exception("API error")

        with pytest.raises(MCPToolError):
            await search_europepmc(mock_ctx, "test")
        mock_ctx.error.assert_called()
