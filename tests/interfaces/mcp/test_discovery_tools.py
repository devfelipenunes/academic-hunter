"""Tests for discovery MCP tools (citation graph, DOI fetch, topic discovery).

Uses mock_ctx from conftest and patches requests or AcademicHunter.
"""

import json
from unittest.mock import patch

import pytest

from academic_hunter.interfaces.mcp.exceptions import MCPToolError
from academic_hunter.interfaces.mcp.tools.discovery import (
    explore_citation_graph,
    fetch_multiple_abstracts,
    fetch_paper_by_doi,
    quick_topic_discovery,
)


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
async def test_quick_topic_discovery_returns_evidence_not_a_configuration(
    mock_get, mock_ctx, mock_openalex, openalex_response
):
    """The terms come from the field's own titles; the shape does not come at all.

    The reply used to be a finished draft -- one anchor group, one technical
    category, every weight flat at 1.5 -- built from the ten titles retrieved.
    Ten titles are not a field, and for an ambiguous topic the sample is mostly
    off-topic, so the frequency count lifts the words every field uses to the
    height of the topic's own. A shape handed over is a shape kept: an agent
    revises the numbers it was given and keeps the frame.

    The counts still come from the titles, because that part was always worth
    having. Writing ``technical_strings`` for a topic one has only just been
    told about is guesswork, and an empty or guessed mapping leaves four of the
    six sources unqueried.
    """
    mock_get.return_value = openalex_response(
        {
            "results": [
                {
                    "display_name": "Distributed ledger settlement in central banks",
                    "publication_year": 2021,
                },
                {
                    "display_name": "Distributed ledger and monetary policy",
                    "publication_year": 2022,
                },
            ]
        }
    )

    result = await quick_topic_discovery("tokenised settlement rails", mock_ctx)

    assert "Draft configuration" not in result
    payload = json.loads(result[result.index("{") :])

    assert payload["titles_counted"] == 2
    assert "anchors" not in payload
    assert "technical_strings" not in payload
    assert "technical_weights" not in payload

    counts = {entry["term"]: entry["titles"] for entry in payload["candidate_terms"]}
    assert counts["distributed ledger"] == 2, (
        "the recurring phrase from the titles is the evidence the reply exists to give"
    )


@patch("academic_hunter.interfaces.mcp.tools.discovery.requests.get")
async def test_quick_topic_discovery_counts_a_hundred_titles(
    mock_get, mock_ctx, mock_openalex, openalex_response
):
    """A hundred titles are counted, because the hundredth costs nothing.

    OpenAlex prices a `search` by call type rather than by result count -- ten
    credits for the request -- so the ten-title page was buying a tenth of the
    evidence for the whole price.
    """
    mock_get.return_value = openalex_response({"results": []})

    await quick_topic_discovery("anything", mock_ctx)

    assert mock_get.call_args.kwargs["params"]["per_page"] == 100


@patch("academic_hunter.interfaces.mcp.tools.discovery.requests.get")
async def test_quick_topic_discovery_shows_fewer_titles_than_it_counts(
    mock_get, mock_ctx, mock_openalex, openalex_response
):
    """The sample grows; the printed list does not.

    Every fetched title used to be printed. Raising the fetch without capping
    the print would put a hundred titles into the agent's context -- and for an
    ambiguous topic most of them are the off-topic ones the counts are supposed
    to be judged against.
    """
    mock_get.return_value = openalex_response(
        {
            "results": [
                {
                    "display_name": f"Ledger settlement study {i}",
                    "publication_year": 2023,
                }
                for i in range(40)
            ]
        }
    )

    result = await quick_topic_discovery("ledger settlement", mock_ctx)

    listed = [line for line in result.splitlines() if line.startswith("- ")]
    assert len(listed) == 10
    assert "30 more, not shown" in result
    payload = json.loads(result[result.index("{") :])
    assert payload["titles_counted"] == 40


def test_candidate_terms_marks_a_generic_word_without_dropping_it():
    """A generic term is flagged, not deleted: scoring on it is still fair.

    Measured on a real run, ``framework`` matched 316 of 1151 papers and
    ``accuracy`` 424 -- more than the topic's own core term. Frequency alone
    cannot separate a field's vocabulary from every field's, so the counts say
    which is which and leave the choice with the caller. Deleting them hides the
    choice; making one an anchor widens the gate to every paper using the word.
    """
    from academic_hunter.interfaces.mcp.tools.discovery import _candidate_terms

    payload = _candidate_terms(
        ["A framework for accurate quantization", "A framework for fast inference"]
    )
    entries = {entry["term"]: entry for entry in payload["candidate_terms"]}

    assert entries["framework"]["generic"] is True
    assert entries["framework"]["titles"] == 2
    assert "generic" not in entries["quantization"]


def test_candidate_terms_keeps_a_phrase_that_contains_a_generic_word():
    """Only a phrase that is generic word for word counts as generic.

    ``deep learning`` and ``language model`` keep their meaning next to a
    generic word, and flagging them would mark the topic's own vocabulary as
    noise. ``framework evaluation`` is generic in both words and is flagged.
    """
    from academic_hunter.interfaces.mcp.tools.discovery import _candidate_terms

    common = _candidate_terms(["Deep learning for language model compression"])
    common_entries = {e["term"]: e for e in common["candidate_terms"]}
    assert "generic" not in common_entries["deep learning"]
    assert "generic" not in common_entries["language model"]

    generic = _candidate_terms(["framework evaluation across the field"])
    generic_entries = {e["term"]: e for e in generic["candidate_terms"]}
    assert generic_entries["framework evaluation"]["generic"] is True


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


_ASTRO = [
    "Stellar Populations in the Local Group",
    "MESA Isochrones and Stellar Evolution",
]


@patch("academic_hunter.interfaces.mcp.tools.discovery.requests.get")
async def test_the_discovery_keeps_the_titles_it_counted(
    mock_get, mock_ctx, mock_openalex, openalex_response
):
    """The titles were swept, counted, and thrown away.

    For the topic "Stellar" the sweep returned stellar populations and MESA
    isochrones -- in the literature that word is an adjective for stars -- and a
    configuration for the Stellar blockchain was written over it from memory.
    `update_config` can only hold the anchors against that literature if the
    titles it counted are still somewhere to be read.
    """
    from academic_hunter.interfaces.mcp.cache import discovery_titles

    mock_get.return_value = openalex_response(
        {
            "results": [
                {"display_name": _ASTRO[0], "publication_year": 2021},
                {"display_name": _ASTRO[1], "publication_year": 2022},
            ]
        }
    )

    await quick_topic_discovery("Stellar", mock_ctx)

    record = discovery_titles.get("Stellar")
    assert record["topic"] == "Stellar"
    assert record["titles"] == _ASTRO
    assert record["candidates"]["titles_counted"] == 2


@patch("academic_hunter.interfaces.mcp.tools.discovery.requests.get")
async def test_a_discovery_that_found_nothing_records_nothing(
    mock_get, mock_ctx, mock_openalex, openalex_response
):
    """An empty success is still cached, and a missing record has to read as
    "nothing to check" rather than as every anchor having missed."""
    from academic_hunter.interfaces.mcp.cache import discovery_titles

    mock_get.return_value = openalex_response({"results": []})

    result = await quick_topic_discovery("a topic nobody wrote about", mock_ctx)

    assert "No results found" in result
    assert discovery_titles.size == 0


@patch("academic_hunter.interfaces.mcp.tools.discovery.requests.get")
async def test_the_evidence_outlives_a_reply_the_cache_serves(
    mock_get, mock_ctx, mock_openalex, openalex_response
):
    """`@cached` runs the body only on a miss, so the store that body fills has
    to outlive the reply it belongs to.

    If the titles expired first, a reply served from `discovery_cache` would be
    handed back while the evidence behind it was already gone, and the check
    that reads it would go quiet in exactly the case it exists for.
    """
    from academic_hunter.interfaces.mcp.cache import discovery_cache, discovery_titles

    assert discovery_titles._ttl >= discovery_cache._ttl

    mock_get.return_value = openalex_response(
        {"results": [{"display_name": _ASTRO[0], "publication_year": 2021}]}
    )

    await quick_topic_discovery("Stellar", mock_ctx)
    await quick_topic_discovery("Stellar", mock_ctx)

    assert mock_get.call_count == 1
    assert discovery_titles.get("Stellar")["titles"] == [_ASTRO[0]]
