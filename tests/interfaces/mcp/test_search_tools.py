import os
import pytest
from unittest.mock import patch, MagicMock
from academic_hunter.interfaces.mcp.tools.search import run_search, read_latest_report

@patch("academic_hunter.interfaces.mcp.tools.search.AcademicHunter")
def test_run_search(mock_hunter_class):
    mock_instance = MagicMock()
    fake_report_path = os.path.join(os.getcwd(), "results", "RELATORIO_ELITE_123.md")
    mock_instance.run.return_value = fake_report_path
    mock_hunter_class.return_value = mock_instance
    
    result = run_search(limit_per_source=2)
    
    mock_instance.run.assert_called_once_with(limit_per_source=2)
    assert "Search completed successfully" in result
    assert "RELATORIO_ELITE_123.md" in result

def test_read_latest_report(tmp_path):
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    
    # Create a fake report
    report_file = results_dir / "RELATORIO_ELITE_test.md"
    report_file.write_text("# Fake Report\nThis is a test.")
    
    try:
        result = read_latest_report()
        assert "Fake Report" in result
    finally:
        os.chdir(old_cwd)

def test_read_latest_report_no_dir(tmp_path):
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        result = read_latest_report()
        assert "Error" in result or "No results directory" in result
    finally:
        os.chdir(old_cwd)
