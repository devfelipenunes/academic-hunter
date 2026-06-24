import os
import sqlite3
import pytest
from academic_hunter.interfaces.mcp.memory.sqlite_store import MCPDatabaseManager

@pytest.fixture
def temp_db(tmp_path):
    # Usamos o diretório temporário do pytest para isolar o banco
    db_path = str(tmp_path / "test_history.db")
    return db_path

def test_db_initialization(temp_db):
    # Garantir que o banco não existe antes
    assert not os.path.exists(temp_db)
    
    manager = MCPDatabaseManager(db_path=temp_db)
    
    # Garantir que o banco foi criado
    assert os.path.exists(temp_db)
    
    # Garantir que a tabela config_history foi criada
    with sqlite3.connect(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='config_history'")
        assert cursor.fetchone() is not None

def test_save_and_get_config(temp_db):
    manager = MCPDatabaseManager(db_path=temp_db)
    
    test_config = {
        "settings": {"test": 123},
        "anchors": {"A": ["B", "C"]}
    }
    
    # Testar o Insert
    config_id = manager.save_config("Test Topic", test_config)
    assert config_id == 1
    
    # Testar a recuperação
    recovered_config = manager.get_config(config_id)
    assert recovered_config is not None
    assert recovered_config["settings"]["test"] == 123
    assert recovered_config["anchors"]["A"] == ["B", "C"]

def test_list_configs_pagination(temp_db):
    manager = MCPDatabaseManager(db_path=temp_db)
    
    # Inserir 15 configs
    for i in range(15):
        manager.save_config(f"Topic {i}", {"index": i})
        
    # Listar as últimas 5
    configs = manager.list_configs(limit=5)
    
    # Garantir que vieram apenas 5
    assert len(configs) == 5
    
    # Garantir que a ordem é DESC (as mais recentes primeiro)
    assert configs[0]["topic"] == "Topic 14"
    assert configs[1]["topic"] == "Topic 13"

def test_get_config_not_found(temp_db):
    manager = MCPDatabaseManager(db_path=temp_db)
    # Tentar recuperar um ID que não existe
    result = manager.get_config(999)
    assert result is None
