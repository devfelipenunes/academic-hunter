import os
import json
import pytest
from unittest.mock import patch, MagicMock
from academic_hunter.interfaces.mcp.tools import read_config, update_config, run_search, SearchConfigUpdate

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
    """Testa se update_config salva novos parâmetros corretamente (usando Pydantic)."""
    # Em FastMCP, o payload do cliente MCP será validado e transformado nesta classe
    config_update = SearchConfigUpdate(
        settings={"start_year": 2024},
        technical_weights={"new": 2.0}
    )
    
    result = update_config(config_update)
    assert "atualizadas com sucesso" in result.lower() or "updated successfully" in result.lower()
    
    with open(temp_config_file, "r") as f:
        saved_data = json.load(f)
        
    assert saved_data["settings"]["start_year"] == 2024
    assert saved_data["technical_weights"]["new"] == 2.0

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

@patch("academic_hunter.interfaces.mcp.tools.requests.get")
def test_explore_citation_graph(mock_get):
    """Testa a ferramenta de snowballing (busca de citações via API externa direta)."""
    from academic_hunter.interfaces.mcp.tools import explore_citation_graph
    
    # Configura o mock do requests para simular a API do Semantic Scholar
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [
            {"citingPaper": {"paperId": "123", "title": "Citing Paper A", "year": 2024}}
        ]
    }
    mock_get.return_value = mock_response
    
    result = explore_citation_graph(doi="10.1000/182", direction="citations")
    
    assert "Citing Paper A" in result
    assert "2024" in result
    mock_get.assert_called_once()
