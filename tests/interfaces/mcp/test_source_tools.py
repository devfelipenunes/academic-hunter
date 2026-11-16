"""One tool, six sources, and the parsers that did not merge.

`search_source` replaced five tools that shared a request block and a Markdown
head but not their parsing. The per-source cases below moved here from the five
files those tools had, because the behaviour they pin is now reached through a
parameter rather than through a name — and pinning it is what says the collapse
changed the surface and not the answers.
"""

from unittest.mock import MagicMock, patch

import pytest

from academic_hunter.interfaces.mcp.exceptions import MCPToolError
from academic_hunter.interfaces.mcp.tools.sources import SOURCE_NAMES, search_source

GET = "academic_hunter.interfaces.mcp.tools.sources.requests.get"
POST = "academic_hunter.interfaces.mcp.tools.sources.requests.post"


def responding(payload, method=GET):
    """A patcher for one source's HTTP call, returning ``payload``."""
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = payload
    return patch(method, return_value=response)


def _mock(payload):
    response = MagicMock()
    response.json.return_value = payload
    return response


OPENAIR = {
    "response": {
        "results": {
            "result": [
                {
                    "metadata": {
                        "oaf:entity": {
                            "oaf:result": {
                                "title": [{"@classid": "main title", "$": "Blockchain for Healthcare"}],
                                "creator": [{"$": "Alice Smith"}, {"$": "Bob Jones"}],
                                "dateofacceptance": {"$": "2024-03-15"},
                                "pid": [{"@classid": "doi", "$": "10.1000/test"}],
                                "bestaccessright": {"@classid": "OPEN ACCESS"},
                                "project": [{"funder": {"$": "European Commission"}}],
                            }
                        }
                    }
                }
            ]
        }
    }
}

DATACITE = {
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

PATENTS = {
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


@pytest.fixture(autouse=True)
def lens_token(monkeypatch):
    """Lens serves no anonymous caller; these cases are about parsing, not auth."""
    monkeypatch.setenv("LENS_API_KEY", "test-token")


async def test_openaire_renders_a_funded_open_access_paper(mock_ctx):
    with responding(OPENAIR):
        result = await search_source(mock_ctx, "openaire", "blockchain healthcare", limit=5)

    assert "Blockchain for Healthcare" in result
    assert "✅ OA" in result
    assert "European Commission" in result
    mock_ctx.info.assert_called()


async def test_openaire_reports_api_match_count(mock_ctx):
    payload = {
        "response": {
            "header": {"numFound": 73},
            "results": {"result": OPENAIR["response"]["results"]["result"]},
        }
    }
    with responding(payload):
        result = await search_source(mock_ctx, "openaire", "blockchain healthcare", limit=1)

    assert "**Total:** 73" in result


async def test_openaire_with_nothing_found(mock_ctx):
    with responding({"response": {"results": []}}):
        result = await search_source(mock_ctx, "openaire", "zzzzznothing")

    assert "No results found" in result


async def test_datacite_renders_a_dataset(mock_ctx):
    with responding(DATACITE):
        result = await search_source(
            mock_ctx, "datacite", "cancer genomics", limit=5, resource_type="dataset"
        )

    assert "Genomic Dataset" in result
    assert "Dataset" in result
    assert "10.5281" in result
    assert "Zenodo" in result


async def test_datacite_reports_api_match_count(mock_ctx):
    payload = {**DATACITE, "meta": {"total": 91}}
    with responding(payload):
        result = await search_source(mock_ctx, "datacite", "cancer genomics", limit=1)

    assert "**Total:** 91" in result


async def test_datacite_sends_the_resource_type_only_when_it_is_given(mock_ctx):
    """The one argument with no analogue in the other five sources."""
    with patch(GET) as m_get:
        m_get.return_value = MagicMock(json=MagicMock(return_value=DATACITE))
        await search_source(mock_ctx, "datacite", "q", resource_type="dataset")
        assert m_get.call_args.kwargs["params"]["resource-type-id"] == "dataset"

    with patch(GET) as m_get:
        m_get.return_value = MagicMock(json=MagicMock(return_value=DATACITE))
        await search_source(mock_ctx, "datacite", "q")
        assert "resource-type-id" not in m_get.call_args.kwargs["params"]


async def test_datacite_with_nothing_found(mock_ctx):
    with responding({"data": []}):
        result = await search_source(mock_ctx, "datacite", "zzzzznothing")

    assert "No results" in result


async def test_lens_renders_patents_with_their_inventors(mock_ctx):
    with responding(PATENTS, method=POST):
        result = await search_source(mock_ctx, "lens", "blockchain", limit=5)

    assert "Blockchain Consensus Method" in result
    assert "Alice Smith" in result
    mock_ctx.info.assert_called()


async def test_lens_reports_api_match_count(mock_ctx):
    payload = {**PATENTS, "total": 118}
    with responding(payload, method=POST):
        result = await search_source(mock_ctx, "lens", "blockchain", limit=1)

    assert "**Total:** 118" in result


async def test_lens_with_nothing_found(mock_ctx):
    with responding({"data": []}, method=POST):
        result = await search_source(mock_ctx, "lens", "zzzzzznothing")

    assert "No patents found" in result


async def test_an_unknown_source_lists_the_ones_that_exist(mock_ctx):
    """It replaced a `server=` argument, so the reply is where the names live now."""
    result = await search_source(mock_ctx, "not-a-source", "test")

    assert "Unsupported source" in result
    for name in SOURCE_NAMES:
        assert name in result


@pytest.mark.parametrize(
    "source,method",
    [("openaire", GET), ("datacite", GET), ("lens", POST)],
)
async def test_a_failing_source_raises_the_tool_error_the_agent_expects(
    mock_ctx, source, method
):
    with patch(method, side_effect=Exception("API error")):
        with pytest.raises(MCPToolError):
            await search_source(mock_ctx, source, "test")

    mock_ctx.error.assert_called()
