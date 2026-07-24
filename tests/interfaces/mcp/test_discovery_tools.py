"""Tests for discovery MCP tools (citation graph, DOI fetch, topic discovery).

Uses mock_ctx from conftest and patches requests or AcademicHunter.
"""

import pytest
from unittest.mock import patch, MagicMock
from academic_hunter.interfaces.mcp.tools.discovery import (
    explore_citation_graph,
    fetch_paper_by_doi,
    fetch_multiple_abstracts,
    quick_topic_discovery,
)
from academic_hunter.interfaces.mcp.exceptions import MCPToolError


# ── explore_citation_graph ────────────────────────────────────────────────────


@patch("academic_hunter.interfaces.mcp.tools.discovery.requests.get")
async def test_explore_citation_graph(mock_get, mock_ctx):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [
            {
                "citingPaper": {
                    "paperId": "123",
                    "title": "Citing Paper A",
                    "year": 2024,
                }
            }
        ]
    }
    mock_get.return_value = mock_response

    result = await explore_citation_graph("10.1000/182", ctx=mock_ctx)

    assert "Citing Paper A" in result
    assert "2024" in result
    mock_ctx.info.assert_called()
    mock_get.assert_called_once()


@patch("academic_hunter.interfaces.mcp.tools.discovery.requests.get")
async def test_explore_citation_graph_api_error(mock_get, mock_ctx):
    mock_get.side_effect = RuntimeError("API timeout")

    with pytest.raises(MCPToolError, match="API timeout"):
        await explore_citation_graph("10.1000/182", ctx=mock_ctx)
    mock_ctx.error.assert_called()


@patch("academic_hunter.interfaces.mcp.tools.discovery.requests.get")
async def test_explore_citation_graph_no_data(mock_get, mock_ctx):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": []}
    mock_get.return_value = mock_response

    result = await explore_citation_graph("10.1000/182", ctx=mock_ctx)
    assert "No citations found" in result


# ── fetch_paper_by_doi ────────────────────────────────────────────────────────


async def test_fetch_paper_by_doi(mock_discovery_hunter, mock_ctx):
    result = await fetch_paper_by_doi("10.1234/test", mock_ctx)
    assert "Abstract of a groundbreaking paper" in result
    mock_ctx.info.assert_called()


async def test_fetch_paper_by_doi_not_found(mock_discovery_hunter, mock_ctx):
    mock_discovery_hunter.fetch_abstract_by_doi.return_value = None

    result = await fetch_paper_by_doi("10.1234/unknown", mock_ctx)
    assert "No abstract could be retrieved" in result


async def test_fetch_paper_by_doi_error(mock_discovery_hunter, mock_ctx):
    mock_discovery_hunter.fetch_abstract_by_doi.side_effect = RuntimeError(
        "API unavailable"
    )

    with pytest.raises(MCPToolError, match="API unavailable"):
        await fetch_paper_by_doi("10.1234/test", mock_ctx)
    mock_ctx.error.assert_called()


# ── fetch_multiple_abstracts ──────────────────────────────────────────────────


async def test_fetch_multiple_abstracts(mock_discovery_hunter, mock_ctx):
    mock_discovery_hunter.fetch_abstract_by_doi.side_effect = (
        lambda doi: f"Abstract for {doi}"
    )

    dois = ["10.1/A", "10.2/B"]
    result = await fetch_multiple_abstracts(dois, mock_ctx)

    assert "Abstract for 10.1/A" in result
    assert "Abstract for 10.2/B" in result
    assert mock_discovery_hunter.fetch_abstract_by_doi.call_count == 2
    mock_ctx.info.assert_called()


async def test_fetch_multiple_abstracts_error(mock_discovery_hunter, mock_ctx):
    mock_discovery_hunter.fetch_abstract_by_doi.side_effect = RuntimeError("crash")

    with pytest.raises(MCPToolError, match="crash"):
        await fetch_multiple_abstracts(["10.1/A"], mock_ctx)
    mock_ctx.error.assert_called()


# ── quick_topic_discovery ─────────────────────────────────────────────────────


@patch("academic_hunter.interfaces.mcp.tools.discovery.requests.get")
async def test_quick_topic_discovery(mock_get, mock_ctx):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [
            {"title": "Government Blockchain Use Cases"},
            {"title": "CBDC and the Future"},
        ]
    }
    mock_get.return_value = mock_response

    result = await quick_topic_discovery("government blockchain", mock_ctx)

    assert "Government Blockchain Use Cases" in result
    assert "CBDC" in result
    mock_ctx.info.assert_called()
    mock_get.assert_called_once()


@patch("academic_hunter.interfaces.mcp.tools.discovery.requests.get")
async def test_quick_topic_discovery_no_results(mock_get, mock_ctx):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": []}
    mock_get.return_value = mock_response

    result = await quick_topic_discovery("unknown", mock_ctx)
    assert "No results found" in result


@patch("academic_hunter.interfaces.mcp.tools.discovery.requests.get")
async def test_quick_topic_discovery_api_error(mock_get, mock_ctx):
    mock_get.side_effect = RuntimeError("API limit exceeded")

    with pytest.raises(MCPToolError, match="API limit exceeded"):
        await quick_topic_discovery("test", mock_ctx)
    mock_ctx.error.assert_called()
