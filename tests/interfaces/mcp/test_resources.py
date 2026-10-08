"""Tests for MCP Resource endpoints.

Verifies that:
- ``get_config_resource`` returns current config as JSON.
- ``get_latest_report_resource`` returns report content or fallback.
- ``get_vector_stats_resource`` returns stats JSON or fallback.
- ``get_paper_resource`` returns paper metadata or fallback.
"""

import json
from unittest.mock import MagicMock, patch


async def test_get_config_resource_returns_config(mock_ctx):
    """Returns the current HunterConfig as formatted JSON."""
    from academic_hunter.interfaces.mcp.resources import get_config_resource

    config_data = {
        "settings": {"start_year": 2020, "limit_per_query": 100},
        "anchors": {"Cat": ["term"]},
        "technical_strings": {"Tech": ["blockchain"]},
        "technical_weights": {"blockchain": 5.0},
        "context_rules": {},
        "keyword_only_terms": [],
        "keyword_only_category": "",
        "blocked_sources": [],
    }

    with patch("academic_hunter.core.get_config") as m_get_config:
        mock_cfg = MagicMock()
        mock_cfg.settings = config_data["settings"]
        mock_cfg.public_settings = MagicMock(return_value=config_data["settings"])
        mock_cfg.anchors = config_data["anchors"]
        mock_cfg.tech_strings = config_data["technical_strings"]
        mock_cfg.tech_weights = config_data["technical_weights"]
        mock_cfg.context_rules = config_data["context_rules"]
        mock_cfg.keyword_only_terms = config_data["keyword_only_terms"]
        mock_cfg.keyword_only_category = config_data["keyword_only_category"]
        mock_cfg.blocked_sources = set()
        m_get_config.return_value = mock_cfg

        result = await get_config_resource()
        parsed = json.loads(result)

    assert parsed["settings"]["start_year"] == 2020
    assert parsed["anchors"] == {"Cat": ["term"]}
    assert parsed["technical_weights"]["blockchain"] == 5.0


async def test_get_config_resource_format(mock_ctx):
    """Returns indented JSON for readability."""
    from academic_hunter.interfaces.mcp.resources import get_config_resource

    with patch("academic_hunter.core.get_config") as m:
        mock_cfg = MagicMock()
        mock_cfg.settings = {}
        mock_cfg.public_settings = MagicMock(return_value={})
        mock_cfg.anchors = {}
        mock_cfg.tech_strings = {}
        mock_cfg.tech_weights = {}
        mock_cfg.context_rules = {}
        mock_cfg.keyword_only_terms = []
        mock_cfg.keyword_only_category = ""
        mock_cfg.blocked_sources = set()
        m.return_value = mock_cfg

        result = await get_config_resource()
    assert "\n" in result
    assert '  "settings"' in result


async def test_get_latest_report_resource_no_dir(mock_ctx, tmp_path):
    """Returns fallback when results directory does not exist."""
    from academic_hunter.interfaces.mcp.resources import get_latest_report_resource

    with patch("academic_hunter.interfaces.mcp.tools._utils.get_project_root") as m:
        m.return_value = tmp_path / "nonexistent"
        result = await get_latest_report_resource()
    assert result == "No report available"


async def test_get_latest_report_resource_no_md(mock_ctx, tmp_path):
    """Returns fallback when no .md files exist."""
    from academic_hunter.interfaces.mcp.resources import get_latest_report_resource

    results_dir = tmp_path / "results"
    results_dir.mkdir()
    with patch("academic_hunter.interfaces.mcp.tools._utils.get_project_root") as m:
        m.return_value = tmp_path
        result = await get_latest_report_resource()
    assert result == "No report available"


async def test_get_latest_report_resource_returns_content(mock_ctx, tmp_path):
    """Returns content of the most recent .md file."""
    from academic_hunter.interfaces.mcp.resources import get_latest_report_resource

    results_dir = tmp_path / "results"
    results_dir.mkdir()
    report = results_dir / "report_latest.md"
    report.write_text("# Test Report\n\nSome content here.", encoding="utf-8")

    with patch("academic_hunter.interfaces.mcp.tools._utils.get_project_root") as m:
        m.return_value = tmp_path
        result = await get_latest_report_resource()
    assert "# Test Report" in result
    assert "Some content here" in result


async def test_get_latest_report_resource_says_when_it_cut_the_report(mock_ctx, tmp_path):
    """A bare slice ends mid-sentence and reads as the report's own ending.

    The resource is the read a client summarises a run from, and a report is the
    one artifact whose tail is the conclusion. Cutting it silently hands over a
    fragment that looks whole.
    """
    from academic_hunter.interfaces.mcp.resources import get_latest_report_resource

    results_dir = tmp_path / "results"
    results_dir.mkdir()
    long_text = "A" * 15000
    report = results_dir / "report_long.md"
    report.write_text(long_text, encoding="utf-8")

    with patch("academic_hunter.interfaces.mcp.tools._utils.get_project_root") as m:
        m.return_value = tmp_path
        result = await get_latest_report_resource()

    assert result.startswith("A" * 100)
    assert "truncated" in result.lower(), "the report just stopped, unannounced"
    assert "5000" in result, "the reader was not told how much is missing"


async def test_get_latest_report_resource_leaves_a_short_report_alone(mock_ctx, tmp_path):
    from academic_hunter.interfaces.mcp.resources import get_latest_report_resource

    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "report_short.md").write_text("# Report\n\nAll of it.", encoding="utf-8")

    with patch("academic_hunter.interfaces.mcp.tools._utils.get_project_root") as m:
        m.return_value = tmp_path
        result = await get_latest_report_resource()

    assert result == "# Report\n\nAll of it."


async def test_get_vector_stats_resource_not_available(mock_ctx):
    """Returns fallback JSON when vector store is None."""
    from academic_hunter.interfaces.mcp.resources import get_vector_stats_resource

    with patch("academic_hunter.interfaces.mcp.tools._utils._get_vector_store") as m:
        m.return_value = None
        result = await get_vector_stats_resource()
    parsed = json.loads(result)
    assert parsed["available"] is False


async def test_get_vector_stats_resource_available(mock_ctx):
    """Returns stats JSON when vector store is available."""
    from academic_hunter.interfaces.mcp.resources import get_vector_stats_resource

    mock_store = MagicMock()
    mock_store.list_collections.return_value = ["papers"]
    mock_store.collection_stats.return_value = {"count": 42, "name": "papers"}

    with patch("academic_hunter.interfaces.mcp.tools._utils._get_vector_store") as m:
        m.return_value = mock_store
        result = await get_vector_stats_resource()
    parsed = json.loads(result)
    assert parsed["available"] is True
    assert parsed["total_papers"] == 42
    assert parsed["collection_count"] == 1


async def test_get_vector_stats_resource_multiple_collections(mock_ctx):
    """Handles multiple collections."""
    from academic_hunter.interfaces.mcp.resources import get_vector_stats_resource

    mock_store = MagicMock()
    mock_store.list_collections.return_value = ["papers", "embeddings"]
    mock_store.collection_stats.side_effect = [
        {"count": 10, "name": "papers"},
        {"count": 20, "name": "embeddings"},
    ]

    with patch("academic_hunter.interfaces.mcp.tools._utils._get_vector_store") as m:
        m.return_value = mock_store
        result = await get_vector_stats_resource()
    parsed = json.loads(result)
    assert parsed["available"] is True
    assert parsed["total_papers"] == 30
    assert parsed["collection_count"] == 2


async def test_get_paper_resource_found(mock_ctx):
    """Returns paper metadata when found."""
    from academic_hunter.interfaces.mcp.resources import get_paper_resource

    with patch("academic_hunter.AcademicHunter") as m_hunter:
        instance = m_hunter.return_value
        instance.fetch_abstract_by_doi.return_value = "This is an interesting abstract."
        result = await get_paper_resource("10.1000/test_doi")
    parsed = json.loads(result)
    assert parsed["doi"] == "10.1000/test_doi"
    assert parsed["found"] is True
    assert "abstract" in parsed


async def test_get_paper_resource_not_found(mock_ctx):
    """Returns not-found metadata when abstract is missing."""
    from academic_hunter.interfaces.mcp.resources import get_paper_resource

    with patch("academic_hunter.AcademicHunter") as m_hunter:
        instance = m_hunter.return_value
        instance.fetch_abstract_by_doi.return_value = ""
        result = await get_paper_resource("10.1000/missing")
    parsed = json.loads(result)
    assert parsed["found"] is False


async def test_get_paper_resource_error(mock_ctx):
    """Returns error info when exception occurs."""
    from academic_hunter.interfaces.mcp.resources import get_paper_resource

    with patch("academic_hunter.AcademicHunter") as m_hunter:
        instance = m_hunter.return_value
        instance.fetch_abstract_by_doi.side_effect = Exception("API Error")
        result = await get_paper_resource("10.1000/error_doi")
    parsed = json.loads(result)
    assert parsed["found"] is False
    assert "error" in result


async def test_the_doi_resource_answers_through_the_uri_template(mock_ctx):
    """The three tests above call the handler directly, so none of them could
    see that the URI it is registered under reaches no handler for a real DOI.

    A DOI's slash never crosses the `{doi}` segment the template matches, and
    the percent-encoded form — the only one that matches — arrives still
    encoded. This reads through the template, which is what a client does, and
    pins both halves: the route answers, and the handler is given the DOI.
    """
    from academic_hunter.interfaces.mcp.server import create_mcp_server

    server = create_mcp_server()
    with patch("academic_hunter.AcademicHunter") as m_hunter:
        m_hunter.return_value.fetch_abstract_by_doi.return_value = "An abstract."
        contents = await server.read_resource(
            "academic-hunter://papers/10.1000%2Ftest_doi"
        )

    parsed = json.loads(contents[0].content)
    assert parsed["found"] is True
    assert parsed["doi"] == "10.1000/test_doi"
    assert parsed["abstract"] == "An abstract."
    m_hunter.return_value.fetch_abstract_by_doi.assert_called_once_with("10.1000/test_doi")


async def test_the_doi_resource_says_the_doi_must_be_encoded(mock_ctx):
    """The description is the only place an agent can learn the encoding.

    A resource whose URI cannot be built from the documentation is one the agent
    never reads, and it fails as "Unknown resource" — which says nothing about
    the encoding that would have worked.
    """
    from academic_hunter.interfaces.mcp.server import create_mcp_server

    server = create_mcp_server()
    template = next(
        t for t in await server.list_resource_templates() if "papers" in str(t.uriTemplate)
    )

    assert "%2F" in (template.description or ""), (
        "an agent reading this description cannot build a URI that matches: "
        f"{template.description!r}"
    )
