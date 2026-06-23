import os
import json
import pytest
from unittest.mock import patch, MagicMock
from academic_hunter.interfaces.mcp.tools import read_config, update_config, run_search

@pytest.fixture
def temp_config_file(tmp_path):
    config_data = {
        "keywords": {"test": 1.0},
        "year_start": 2020
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config_data))
    
    # Mudar o diretório de trabalho para que tools.py ache o config.json e a pasta results
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    
    # Criar pasta results
    (tmp_path / "results").mkdir()
    
    yield config_file
    
    # Restaurar
    os.chdir(old_cwd)


def test_read_config(temp_config_file):
    """Testa se read_config lê corretamente o arquivo json."""
    result = read_config()
    data = json.loads(result)
    assert "settings" in data
    assert data["settings"].get("start_year", 2020) == 2020

def test_update_config(temp_config_file):
    """Testa se update_config salva novos parâmetros corretamente."""
    new_data = {
        "settings": {"start_year": 2024},
        "technical_weights": {"new": 2.0}
    }
    
    result = update_config(json.dumps(new_data))
    assert result == "config.json updated successfully!"
    
    with open(temp_config_file, "r") as f:
        saved_data = json.load(f)
        
    assert saved_data["settings"]["start_year"] == 2024
    assert saved_data["technical_weights"]["new"] == 2.0

def test_update_config_invalid_json():
    """Testa o tratamento de erro se o JSON for inválido."""
    result = update_config("{invalid_json: true")
    assert result == "Error: The provided string is not a valid JSON."

@patch("academic_hunter.interfaces.mcp.tools.AcademicHunter")
def test_run_search(mock_hunter_class, temp_config_file):
    """Testa a execução do run_search e a identificação do relatório."""
    # Configura o mock
    mock_instance = MagicMock()
    # Simula o retorno do path do report pela engine
    fake_report_path = os.path.join(os.getcwd(), "results", "RELATORIO_ELITE_123.md")
    mock_instance.run.return_value = fake_report_path
    mock_hunter_class.return_value = mock_instance
    
    result = run_search(limit_per_source=2)
    
    mock_instance.run.assert_called_once_with(limit_per_source=2)
    assert "Search completed successfully. Report generated at:" in result
    assert "RELATORIO_ELITE_123.md" in result
