"""Tests for export_report tool."""
import pytest
import json
from unittest.mock import patch, MagicMock
from pathlib import Path


async def _export_test(mock_ctx, tmp_path, fmt, papers, expected_content_check=None):
    """Helper: run export_report with nested mocks."""
    from academic_hunter.interfaces.mcp.tools.export import export_report

    with patch("academic_hunter.interfaces.mcp.tools.export.AcademicHunter") as m_h, \
         patch("academic_hunter.interfaces.mcp.tools.export.get_project_root") as m_root, \
         patch(
             "academic_hunter.interfaces.mcp.tools.export._load_latest_papers",
             return_value=list(papers),
         ):
        m_h.return_value.consolidated_results = {str(i): p for i, p in enumerate(papers)}
        m_root.return_value = tmp_path
        result = await export_report(mock_ctx, format=fmt)
    return result


async def test_export_report_csv(mock_ctx, tmp_path):
    """Exports papers in CSV format."""
    papers = [
        {"Title": "Paper One", "DOI": "10.1000/one", "Authors": "Author A"},
        {"Title": "Paper Two", "DOI": "10.1000/two", "Authors": "Author B"},
    ]
    result = await _export_test(mock_ctx, tmp_path, "csv", papers)
    assert "Successfully exported" in result
    assert ".csv" in result
    csv_files = list(tmp_path.glob("results/export_*.csv"))
    assert len(csv_files) == 1
    content = csv_files[0].read_text()
    assert "Paper One" in content
    assert "Paper Two" in content


async def test_export_report_json(mock_ctx, tmp_path):
    """Exports papers in JSON format."""
    papers = [{"Title": "Paper One", "DOI": "10.1000/one"}]
    result = await _export_test(mock_ctx, tmp_path, "json", papers)
    assert "Successfully exported" in result
    json_files = list(tmp_path.glob("results/export_*.json"))
    assert len(json_files) == 1
    data = json.loads(json_files[0].read_text())
    assert len(data) == 1
    assert data[0]["Title"] == "Paper One"


async def test_export_report_bibtex(mock_ctx, tmp_path):
    """Exports papers in BibTeX format."""
    papers = [{"Title": "Paper", "Authors": "Author A", "Year": 2024, "DOI": "10.1000/test"}]
    result = await _export_test(mock_ctx, tmp_path, "bibtex", papers)
    assert "Successfully exported" in result
    bib_files = list(tmp_path.glob("results/export_*.bib"))
    assert len(bib_files) == 1
    content = bib_files[0].read_text()
    assert "@article{" in content


async def test_export_report_ris(mock_ctx, tmp_path):
    """Exports papers in RIS format."""
    papers = [{"Title": "Paper", "Authors": ["Author A"], "Year": 2024, "DOI": "10.1000/test"}]
    result = await _export_test(mock_ctx, tmp_path, "ris", papers)
    assert "Successfully exported" in result
    ris_files = list(tmp_path.glob("results/export_*.ris"))
    assert len(ris_files) == 1
    content = ris_files[0].read_text()
    assert "TY  - JOUR" in content


async def test_export_report_no_results(mock_ctx, tmp_path):
    """Returns message when no results to export."""
    result = await _export_test(mock_ctx, tmp_path, "csv", [])
    assert "No search results to export" in result


async def test_export_report_unsupported_format(mock_ctx, tmp_path):
    """Returns message for unsupported format."""
    result = await _export_test(mock_ctx, tmp_path, "xml", [{"Title": "P"}])
    assert "Unsupported format" in result


async def test_export_report_custom_output_path(mock_ctx, tmp_path):
    """Writes to custom output path when provided."""
    from academic_hunter.interfaces.mcp.tools.export import export_report

    papers = [{"Title": "Paper"}]

    with patch("academic_hunter.interfaces.mcp.tools.export.AcademicHunter") as m_h, \
         patch("academic_hunter.interfaces.mcp.tools.export.get_project_root") as m_root:
        m_h.return_value.consolidated_results = {"0": papers[0]}
        m_root.return_value = tmp_path
        custom_path = str(tmp_path / "custom_export.csv")
        result = await export_report(mock_ctx, format="csv", output_path=custom_path)

    assert custom_path in result
    assert Path(custom_path).exists()


async def test_export_report_fallback_to_csv(mock_ctx, tmp_path):
    """Falls back to latest CSV when no in-memory results."""
    from academic_hunter.interfaces.mcp.tools.export import export_report

    results_dir = tmp_path / "results"
    results_dir.mkdir()
    csv_file = results_dir / "academic_dataset_20240101_120000.csv"
    csv_file.write_text("Title,DOI\nPaper,10.1000/test\n")

    with patch("academic_hunter.interfaces.mcp.tools.export.AcademicHunter") as m_h, \
         patch("academic_hunter.interfaces.mcp.tools.export.get_project_root") as m_root, \
         patch("academic_hunter.interfaces.mcp.tools._utils.get_project_root") as m_utils_root:
        m_h.return_value.consolidated_results = {}
        m_root.return_value = tmp_path
        m_utils_root.return_value = tmp_path
        result = await export_report(mock_ctx, format="json")

    assert "Successfully exported" in result
