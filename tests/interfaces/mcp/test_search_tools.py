import os
import pytest
from unittest.mock import patch, MagicMock
from academic_hunter.interfaces.mcp.search_tools import run_search

@patch("academic_hunter.interfaces.mcp.search_tools.AcademicHunter")
def test_run_search(mock_hunter_class):
    mock_instance = MagicMock()
    fake_report_path = os.path.join(os.getcwd(), "results", "RELATORIO_ELITE_123.md")
    mock_instance.run.return_value = fake_report_path
    mock_hunter_class.return_value = mock_instance
    
    result = run_search(limit_per_source=2)
    
    mock_instance.run.assert_called_once_with(limit_per_source=2)
    assert "Search completed successfully" in result
    assert "RELATORIO_ELITE_123.md" in result
