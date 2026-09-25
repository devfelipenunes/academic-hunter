"""Tests for search MCP tools (run_search, read_latest_report).

Uses mock_ctx from conftest and patches AcademicHunter and get_project_root.
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from academic_hunter.interfaces.mcp.tools.search import run_search, read_latest_report
from academic_hunter.interfaces.mcp.exceptions import MCPToolError


# ── run_search ─────────────────────────────────────────────────────────────────


class _FakeConnector:
    """Enough of a connector for the coverage report to classify it."""

    def __init__(self, keyword_only):
        self.is_keyword_only = keyword_only


@patch("academic_hunter.interfaces.mcp.tools.search.AcademicHunter")
async def test_run_search(mock_hunter_class, mock_ctx):
    mock_instance = MagicMock()
    fake_report_path = os.path.join(os.getcwd(), "results", "RELATORIO_ELITE_123.md")
    mock_instance.run.return_value = fake_report_path
    mock_instance.stats = {"identified": {}, "included_final": 0}
    mock_instance.query_history = []
    mock_instance.connectors = {}
    mock_hunter_class.return_value = mock_instance

    result = await run_search(mock_ctx, limit_per_source=2)

    mock_instance.run.assert_called_once_with(limit_per_source=2)
    assert "Search completed successfully" in result
    assert "RELATORIO_ELITE_123.md" in result
    mock_ctx.info.assert_called()
    mock_ctx.report_progress.assert_called()


@patch("academic_hunter.interfaces.mcp.tools.search.AcademicHunter")
async def test_run_search_failure(mock_hunter_class, mock_ctx):
    mock_instance = MagicMock()
    mock_instance.run.side_effect = RuntimeError("API rate limit exceeded")
    mock_hunter_class.return_value = mock_instance

    with pytest.raises(MCPToolError, match="API rate limit exceeded"):
        await run_search(mock_ctx, limit_per_source=2)
    mock_ctx.error.assert_called()


# ── read_latest_report ────────────────────────────────────────────────────────


@patch("academic_hunter.interfaces.mcp.tools.search.get_project_root")
async def test_read_latest_report(mock_get_project_root, tmp_path, mock_ctx):
    """read_latest_report must respect get_project_root, not os.getcwd()."""
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    mock_get_project_root.return_value = tmp_path

    report_file = results_dir / "RELATORIO_ELITE_test.md"
    report_file.write_text("# Fake Report\nThis is a test.")

    result = await read_latest_report(mock_ctx)
    assert "Fake Report" in result
    mock_ctx.info.assert_called()


@patch("academic_hunter.interfaces.mcp.tools.search.get_project_root")
async def test_read_latest_report_no_dir(mock_get_project_root, tmp_path, mock_ctx):
    """When no results dir exists, the tool should signal an error."""
    mock_get_project_root.return_value = tmp_path

    result = await read_latest_report(mock_ctx)
    assert "Error" in result or "No results directory" in result
    mock_ctx.info.assert_called()


@patch("academic_hunter.interfaces.mcp.tools.search.get_project_root")
async def test_read_latest_report_no_md_files(mock_get_project_root, tmp_path, mock_ctx):
    """Results dir exists but has no markdown files."""
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    # Create a non-md file
    (results_dir / "data.csv").write_text("a,b,c")
    mock_get_project_root.return_value = tmp_path

    result = await read_latest_report(mock_ctx)
    assert "Error" in result or "No markdown reports" in result


@patch("academic_hunter.interfaces.mcp.tools.search.get_project_root")
async def test_read_latest_report_with_offset(mock_get_project_root, tmp_path, mock_ctx):
    """Offset parameter skips the first N characters."""
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    mock_get_project_root.return_value = tmp_path

    report_file = results_dir / "RELATORIO_ELITE_test.md"
    content = "PREFIX" + "ABCDEFGHIJ" * 15  # 6 + 150 = 156 chars
    report_file.write_text(content)

    # Read with offset=6, should skip "PREFIX"
    result = await read_latest_report(mock_ctx, offset=6)
    expected = content[6:]
    assert result == expected
    assert result == "ABCDEFGHIJ" * 15
    assert len(result) == 150
    mock_ctx.info.assert_called()


@patch("academic_hunter.interfaces.mcp.tools.search.get_project_root")
async def test_read_latest_report_custom_max_chars(mock_get_project_root, tmp_path, mock_ctx):
    """Custom max_chars truncates to that exact length."""
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    mock_get_project_root.return_value = tmp_path

    report_file = results_dir / "RELATORIO_ELITE_test.md"
    report_text = "A" * 5000 + "B" * 5000
    report_file.write_text(report_text)

    result = await read_latest_report(mock_ctx, max_chars=100)
    assert len(result) == 100
    assert result == "A" * 100
    mock_ctx.info.assert_called()


@patch("academic_hunter.interfaces.mcp.tools.search.AcademicHunter")
async def test_run_search_refuses_an_empty_config(mock_hunter_class, mock_ctx, tmp_path):
    """The neutral default has no anchors, so a run would query for nothing.

    That is silent degradation: every source is called, nothing scores above the
    threshold, and the tool reports success. The guard turns it into a message
    naming the file and the rung that chose it.
    """
    target = tmp_path / "config.json"
    mock_instance = MagicMock()
    mock_instance.config.is_scorable.return_value = False
    mock_instance.config.config_path = str(target)
    mock_instance.config.config_origin = "packaged_default"
    mock_hunter_class.return_value = mock_instance

    with pytest.raises(MCPToolError) as raised:
        await run_search(mock_ctx, limit_per_source=2)

    assert "packaged_default" in str(raised.value)
    assert str(target) in str(raised.value)
    mock_instance.run.assert_not_called()


@patch("academic_hunter.interfaces.mcp.tools.search.AcademicHunter")
async def test_run_search_proceeds_when_there_is_a_topic(mock_hunter_class, mock_ctx):
    mock_instance = MagicMock()
    mock_instance.config.is_scorable.return_value = True
    mock_instance.run.return_value = os.path.join(os.getcwd(), "results", "RELATORIO_ELITE_1.md")
    mock_instance.stats = {"identified": {}, "included_final": 0}
    mock_instance.query_history = []
    mock_instance.connectors = {}
    mock_hunter_class.return_value = mock_instance

    result = await run_search(mock_ctx, limit_per_source=2)

    assert "Search completed successfully" in result
    mock_instance.run.assert_called_once_with(limit_per_source=2)


@patch("academic_hunter.interfaces.mcp.tools.search.AcademicHunter")
async def test_run_search_separates_a_skipped_source_from_an_empty_one(mock_hunter_class, mock_ctx):
    """Both kinds of source report 0, and they are not the same thing.

    In the run that prompted this, ArXiv and Semantic Scholar both showed 0.
    ArXiv was never called -- technical_strings was empty, so the inner loop
    never executed -- while Semantic Scholar was called and found nothing. The
    reply said both had returned zero, and only one of those was a finding.
    """
    mock_instance = MagicMock()
    mock_instance.config.is_scorable.return_value = True
    mock_instance.config.tech_strings = {}
    mock_instance.run.return_value = os.path.join(os.getcwd(), "results", "RELATORIO_ELITE_1.md")
    mock_instance.query_history = [
        {"Source": "Semantic Scholar", "Query": "CBDC"},
        {"Source": "Crossref", "Query": "CBDC"},
    ]
    mock_instance.stats = {
        "identified": {"ArXiv": 0, "Crossref": 20, "Semantic Scholar": 0},
        "included_final": 5,
    }
    mock_instance.connectors = {
        "ArXiv": _FakeConnector(False),
        "Crossref": _FakeConnector(False),
        "Semantic Scholar": _FakeConnector(True),
    }
    mock_hunter_class.return_value = mock_instance

    result = await run_search(mock_ctx, limit_per_source=2)

    assert "ArXiv: NOT QUERIED" in result
    assert "Semantic Scholar: 0" in result
    assert "Crossref: 20" in result
    assert "Identified: 20 | Included: 5" in result
    assert "ArXiv never ran a query" in result
    assert "technical_strings is empty" in result


@patch("academic_hunter.interfaces.mcp.tools.search.AcademicHunter")
async def test_run_search_stays_quiet_when_every_source_was_queried(mock_hunter_class, mock_ctx):
    """The warning has to mean something, so it cannot fire on a healthy run."""
    mock_instance = MagicMock()
    mock_instance.config.is_scorable.return_value = True
    mock_instance.run.return_value = os.path.join(os.getcwd(), "results", "RELATORIO_ELITE_1.md")
    mock_instance.query_history = [{"Source": "ArXiv", "Query": "CBDC"}, {"Source": "Crossref", "Query": "CBDC"}]
    mock_instance.stats = {"identified": {"ArXiv": 12, "Crossref": 8}, "included_final": 3}
    mock_instance.connectors = {"ArXiv": _FakeConnector(False), "Crossref": _FakeConnector(False)}
    mock_hunter_class.return_value = mock_instance

    result = await run_search(mock_ctx, limit_per_source=2)

    assert "NOT QUERIED" not in result
    assert "never ran a query" not in result
    assert "Identified: 20 | Included: 3" in result


@patch("academic_hunter.interfaces.mcp.tools.search.AcademicHunter")
async def test_run_search_names_the_anchor_gate_when_nothing_reaches_the_scorer(
    mock_hunter_class, mock_ctx
):
    """``Identified: 11 | Included: 0`` reads as an empty field, and it is not one.

    Measured on a real run: the draft put the topic verbatim in as its only
    anchor, no title carried that phrase, and all 11 papers were dropped at the
    anchor gate. The reply reported the two numbers and stopped, leaving the
    caller to conclude the field was empty.
    """
    mock_instance = MagicMock()
    mock_instance.config.is_scorable.return_value = True
    mock_instance.config.anchors = {"Topic": ["CBDC financial stability"]}
    mock_instance.config.tech_strings = {"CBDC financial stability": ["cbdc"]}
    mock_instance.run.return_value = os.path.join(os.getcwd(), "results", "RELATORIO_ELITE_1.md")
    mock_instance.query_history = [{"Source": "Crossref", "Query": "CBDC"}]
    mock_instance.stats = {
        "identified": {"Crossref": 11},
        "excluded_anchors": 11,
        "excluded_technical_score": 0,
        "included_final": 0,
    }
    mock_instance.connectors = {"Crossref": _FakeConnector(False)}
    mock_hunter_class.return_value = mock_instance

    result = await run_search(mock_ctx, limit_per_source=2)

    assert "Identified: 11 | Included: 0" in result
    assert "Nothing reached the scorer" in result
    assert "CBDC financial stability" in result, "the terms to widen are not in the reply"
    assert "11 of the 11 identified papers" in result


@patch("academic_hunter.interfaces.mcp.tools.search.AcademicHunter")
async def test_run_search_stays_quiet_when_the_scorer_did_run(mock_hunter_class, mock_ctx):
    """Anchors that drop some papers are the normal case, not the warning.

    These are the numbers from the same field with the anchors widened: 20
    identified, 7 dropped at the anchor gate, 5 for a low score, 6 included.
    """
    mock_instance = MagicMock()
    mock_instance.config.is_scorable.return_value = True
    mock_instance.run.return_value = os.path.join(os.getcwd(), "results", "RELATORIO_ELITE_1.md")
    mock_instance.query_history = [{"Source": "Crossref", "Query": "CBDC"}]
    mock_instance.stats = {
        "identified": {"Crossref": 20},
        "excluded_anchors": 7,
        "excluded_technical_score": 5,
        "included_final": 6,
    }
    mock_instance.connectors = {"Crossref": _FakeConnector(False)}
    mock_hunter_class.return_value = mock_instance

    result = await run_search(mock_ctx, limit_per_source=2)

    assert "Identified: 20 | Included: 6" in result
    assert "Nothing reached the scorer" not in result
