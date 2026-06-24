import os
import json
import pytest
from unittest.mock import patch
from academic_hunter.interfaces.mcp.config_tools import read_config, update_config, SearchConfigUpdate, list_config_history, restore_config_by_id

@pytest.fixture
def temp_config_file(tmp_path):
    config_data = {
        "keywords": {"test": 1.0},
        "year_start": 2020
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config_data))
    
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    
    yield config_file
    
    os.chdir(old_cwd)

def test_read_config(temp_config_file):
    result = read_config()
    data = json.loads(result)
    assert "settings" in data

def test_update_config_and_history(temp_config_file):
    # Mocking the database to avoid writing to the real `.gemini` folder during tests
    with patch('academic_hunter.interfaces.mcp.config_tools.MCPDatabaseManager') as MockDB:
        mock_db_instance = MockDB.return_value
        
        config_update = SearchConfigUpdate(
            topic="Test Topic",
            settings={"start_year": 2024},
            technical_weights={"new": 2.0}
        )
        result = update_config(config_update)
        assert "sucesso" in result.lower() or "successfully" in result.lower()
        with open(temp_config_file, "r") as f:
            saved_data = json.load(f)
        assert saved_data["settings"]["start_year"] == 2024
        assert saved_data["technical_weights"]["new"] == 2.0
        
        assert mock_db_instance.save_config.call_count == 2

def test_list_config_history():
    with patch('academic_hunter.interfaces.mcp.config_tools.MCPDatabaseManager') as MockDB:
        mock_db_instance = MockDB.return_value
        mock_db_instance.list_configs.return_value = [{"id": 1, "topic": "Test"}]
        
        result = list_config_history()
        assert "Test" in result

def test_restore_config_by_id(temp_config_file):
    with patch('academic_hunter.interfaces.mcp.config_tools.MCPDatabaseManager') as MockDB:
        mock_db_instance = MockDB.return_value
        mock_db_instance.get_config.return_value = {"settings": {"start_year": 1999}}
        
        result = restore_config_by_id(1)
        assert "sucesso" in result.lower() or "successfully" in result.lower()
        
        with open(temp_config_file, "r") as f:
            saved_data = json.load(f)
        assert saved_data["settings"]["start_year"] == 1999
