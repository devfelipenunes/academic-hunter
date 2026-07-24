"""Tests for search MCP tools (run_search, read_latest_report).

Uses mock_ctx from conftest and patches AcademicHunter and get_project_root.
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from academic_hunter.interfaces.mcp.tools.search import run_search, read_latest_report
from academic_hunter.interfaces.mcp.exceptions import MCPToolError


# ── run_search ─────────────────────────────────────────────────────────────────


@patch("academic_hunter.interfaces.mcp.tools.search.AcademicHunter")
async def test_run_search(mock_hunter_class, mock_ctx):
    mock_instance = MagicMock()
    fake_report_path = os.path.join(os.getcwd(), "results", "RELATORIO_ELITE_123.md")
    mock_instance.run.return_value = fake_report_path
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
