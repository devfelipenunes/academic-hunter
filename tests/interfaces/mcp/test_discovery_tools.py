"""Tests for discovery MCP tools (citation graph, DOI fetch, topic discovery).

Uses mock_ctx from conftest and patches requests or AcademicHunter.
"""

import pytest
from unittest.mock import patch
from academic_hunter.interfaces.mcp.tools.discovery import (
    explore_citation_graph,
    fetch_paper_by_doi,
    fetch_multiple_abstracts,
    quick_topic_discovery,
)
from academic_hunter.interfaces.mcp.exceptions import MCPToolError


# ── explore_citation_graph ────────────────────────────────────────────────────


@patch("academic_hunter.interfaces.mcp.tools.discovery.requests.get")
async def test_explore_citation_graph(mock_get, mock_ctx, mock_openalex, openalex_response):
    """`citations` is a DOI singleton followed by a `cites:` filter."""
    mock_get.side_effect = [
        openalex_response(
            {
                "id": "https://openalex.org/W123",
                "display_name": "A Stellar Paper",
                "cited_by_count": 7,
                "referenced_works": [],
            }
        ),
        openalex_response(
            {
                "results": [
                    {"display_name": "Citing Paper A", "publication_year": 2024}
                ]
            }
        ),
    ]

    result = await explore_citation_graph("10.1000/182", ctx=mock_ctx)

    assert "Citing Paper A" in result
    assert "2024" in result
    mock_ctx.info.assert_called()
    assert mock_get.call_count == 2
    # The second call is the one that must be scoped to this work.
    assert mock_get.call_args_list[1].kwargs["params"]["filter"] == "cites:W123"


@patch("academic_hunter.interfaces.mcp.tools.discovery.requests.get")
async def test_explore_citation_graph_marks_preprints(
    mock_get, mock_ctx, mock_openalex, openalex_response
):
    """A preprint and its published version are two works with one title.

    Measured on a real Stellar paper: OpenAlex returned the conference paper and
    its arXiv preprint as separate citing works, so the same title printed twice
    and read as a duplicate. The marker is what distinguishes them.
    """
    mock_get.side_effect = [
        openalex_response({"id": "https://openalex.org/W123"}),
        openalex_response(
            {
                "results": [
                    {
                        "display_name": "Strengthened Fault Tolerance",
                        "publication_year": 2021,
                        "type": "conference-paper",
                    },
                    {
                        "display_name": "Strengthened Fault Tolerance",
                        "publication_year": 2021,
                        "type": "preprint",
                    },
                ]
            }
        ),
    ]

    result = await explore_citation_graph("10.1000/182", ctx=mock_ctx)

    assert "- Strengthened Fault Tolerance (2021)\n" in result
    assert "- Strengthened Fault Tolerance (2021) [preprint]" in result


@patch("academic_hunter.interfaces.mcp.tools.discovery.requests.get")
async def test_explore_citation_graph_references(mock_get, mock_ctx, mock_openalex, openalex_response):
    """`references` resolves the IDs the work carries, in a second call."""
    mock_get.side_effect = [
        openalex_response(
            {
                "id": "https://openalex.org/W123",
                "display_name": "A Stellar Paper",
                "referenced_works": [
                    "https://openalex.org/W1",
                    "https://openalex.org/W2",
                ],
            }
        ),
        openalex_response(
            {
                "results": [
                    {"display_name": "A Referenced Paper", "publication_year": 2019}
                ]
            }
        ),
    ]

    result = await explore_citation_graph(
        "10.1000/182", direction="references", ctx=mock_ctx
    )

    assert "A Referenced Paper" in result
    assert mock_get.call_args_list[1].kwargs["params"]["filter"] == "openalex_id:W1|W2"


@patch("academic_hunter.interfaces.mcp.tools.discovery.requests.get")
async def test_explore_citation_graph_references_not_indexed(
    mock_get, mock_ctx, mock_openalex, openalex_response
):
    """A work with no parsed reference list says so rather than "nothing found".

    OpenAlex indexes many conference papers without their reference list, and an
    empty answer there is not the same claim as "this paper references nothing".
    """
    mock_get.return_value = openalex_response(
        {
            "id": "https://openalex.org/W123",
            "display_name": "A Stellar Paper",
            "cited_by_count": 6,
            "referenced_works": [],
        }
    )

    result = await explore_citation_graph(
        "10.1000/182", direction="references", ctx=mock_ctx
    )

    assert "no indexed reference list" in result
    assert "10.1000/182" in result


@patch("academic_hunter.interfaces.mcp.tools.discovery.requests.get")
async def test_explore_citation_graph_api_error(mock_get, mock_ctx, mock_openalex):
    mock_get.side_effect = RuntimeError("API timeout")

    with pytest.raises(MCPToolError, match="API timeout"):
        await explore_citation_graph("10.1000/182", ctx=mock_ctx)
    mock_ctx.error.assert_called()


@patch("academic_hunter.interfaces.mcp.tools.discovery.requests.get")
async def test_explore_citation_graph_no_data(mock_get, mock_ctx, mock_openalex, openalex_response):
    mock_get.side_effect = [
        openalex_response({"id": "https://openalex.org/W123"}),
        openalex_response({"results": []}),
    ]

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
async def test_quick_topic_discovery(mock_get, mock_ctx, mock_openalex, openalex_response):
    mock_get.return_value = openalex_response(
        {
            "results": [
                {"display_name": "Government Blockchain Use Cases", "publication_year": 2021},
                {"display_name": "CBDC and the Future", "publication_year": 2022},
            ]
        }
    )

    result = await quick_topic_discovery("government blockchain", mock_ctx)

    assert "Government Blockchain Use Cases" in result
    assert "CBDC" in result
    assert "2021" in result
    mock_ctx.info.assert_called()
    mock_get.assert_called_once()


@patch("academic_hunter.interfaces.mcp.tools.discovery.requests.get")
async def test_quick_topic_discovery_sends_the_topic_as_a_parameter(
    mock_get, mock_ctx, mock_openalex, openalex_response
):
    """The topic goes through `params`, not pasted into the URL.

    Built by hand, a topic containing `&` added a query parameter of its own.
    """
    mock_get.return_value = openalex_response({"results": []})

    await quick_topic_discovery("stellar & consensus", mock_ctx)

    assert mock_get.call_args.kwargs["params"]["search"] == "stellar & consensus"


@patch("academic_hunter.interfaces.mcp.tools.discovery.requests.get")
async def test_quick_topic_discovery_no_results(mock_get, mock_ctx, mock_openalex, openalex_response):
    mock_get.return_value = openalex_response({"results": []})

    result = await quick_topic_discovery("unknown", mock_ctx)
    assert "No results found" in result


@patch("academic_hunter.interfaces.mcp.tools.discovery.requests.get")
async def test_quick_topic_discovery_api_error(mock_get, mock_ctx, mock_openalex):
    mock_get.side_effect = RuntimeError("API limit exceeded")

    with pytest.raises(MCPToolError, match="API limit exceeded"):
        await quick_topic_discovery("test", mock_ctx)
    mock_ctx.error.assert_called()
