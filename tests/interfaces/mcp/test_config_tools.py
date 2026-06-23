import os
import json
import pytest
from academic_hunter.interfaces.mcp.config_tools import read_config, update_config, SearchConfigUpdate

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

def test_update_config(temp_config_file):
    config_update = SearchConfigUpdate(
        settings={"start_year": 2024},
        technical_weights={"new": 2.0}
    )
    result = update_config(config_update)
    assert "sucesso" in result.lower() or "successfully" in result.lower()
    with open(temp_config_file, "r") as f:
        saved_data = json.load(f)
    assert saved_data["settings"]["start_year"] == 2024
    assert saved_data["technical_weights"]["new"] == 2.0
