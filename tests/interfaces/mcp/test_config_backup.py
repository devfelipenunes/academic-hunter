import os
import sqlite3
from pathlib import Path

import pytest

from academic_hunter.interfaces.mcp.memory.config_backup import MCPDatabaseManager


@pytest.fixture
def temp_db(tmp_path):
    db_path = str(tmp_path / "test_history.db")
    return db_path

def test_db_initialization(temp_db):
    assert not os.path.exists(temp_db)
    
    manager = MCPDatabaseManager(db_path=temp_db)
    
    assert os.path.exists(temp_db)
    
    with sqlite3.connect(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='config_history'")
        assert cursor.fetchone() is not None

    assert manager.list_configs(limit=1) == []

def test_save_and_get_config(temp_db):
    manager = MCPDatabaseManager(db_path=temp_db)
    
    test_config = {
        "settings": {"test": 123},
        "anchors": {"A": ["B", "C"]}
    }
    
    config_id = manager.save_config("Test Topic", test_config)
    assert config_id == 1
    
    recovered_config = manager.get_config(config_id)
    assert recovered_config is not None
    assert recovered_config["settings"]["test"] == 123
    assert recovered_config["anchors"]["A"] == ["B", "C"]

def test_list_configs_pagination(temp_db):
    manager = MCPDatabaseManager(db_path=temp_db)
    
    for i in range(15):
        manager.save_config(f"Topic {i}", {"index": i})
        
    configs = manager.list_configs(limit=5)
    
    assert len(configs) == 5
    
    assert configs[0]["topic"] == "Topic 14"
    assert configs[1]["topic"] == "Topic 13"

def test_get_config_not_found(temp_db):
    manager = MCPDatabaseManager(db_path=temp_db)
    result = manager.get_config(999)
    assert result is None


def test_the_default_database_lives_in_the_resolved_data_dir(tmp_path, monkeypatch):
    """It used to be written five levels up from ``__file__``.

    In an installed package that path is inside the environment: under ``uvx`` it
    is a cache that is rebuilt at will, so the config history — the thing
    ``restore_config_by_id`` restores from — disappeared with it.
    """
    from academic_hunter.core.infra import paths

    monkeypatch.setenv(paths.DATA_ENV, str(tmp_path / "project"))

    manager = MCPDatabaseManager()

    assert manager.db_path == str(paths.resolve_location().history_db)
    assert os.path.exists(manager.db_path)
    assert str(tmp_path) in manager.db_path


def test_the_default_database_is_never_inside_the_package(tmp_path, monkeypatch):
    from academic_hunter.core.infra import paths

    monkeypatch.setenv(paths.DATA_ENV, str(tmp_path / "project"))

    assert not paths.is_inside_package(Path(MCPDatabaseManager().db_path))


def test_a_negative_limit_is_not_read_as_no_limit(temp_db):
    """SQLite reads ``LIMIT -1`` as "no limit at all".

    A caller asking for -1 to mean "the newest one, whatever the number" got
    the entire table back.
    """
    manager = MCPDatabaseManager(db_path=temp_db)
    for i in range(15):
        manager.save_config(f"Topic {i}", {"index": i})

    assert len(manager.list_configs(limit=-1)) == 1
    assert manager.list_configs(limit=-1)[0]["topic"] == "Topic 14"


def _is_open(conn):
    """A closed SQLite connection refuses to be used."""
    try:
        conn.execute("SELECT 1")
        return True
    except sqlite3.ProgrammingError:
        return False


def test_the_history_does_not_leak_a_connection_per_call(temp_db, monkeypatch):
    """Every read and write opened a connection that was never closed.

    ``with sqlite3.connect(...) as conn`` reads like it closes the database and
    does not: that statement manages a *transaction*, and the handle lives on
    until the garbage collector finalises it. On a long-lived server each tool
    call left one behind, and the history is read on nearly every call.
    """
    opened = []
    real_connect = sqlite3.connect

    def recording_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        opened.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", recording_connect)

    manager = MCPDatabaseManager(db_path=temp_db)
    manager.save_config("Warm-up", {"index": 0})
    manager.list_configs(limit=5)
    manager.get_config(1)

    assert len(opened) >= 3, "the calls did not open the connections this checks"
    still_open = [conn for conn in opened if _is_open(conn)]
    assert not still_open, (
        f"{len(still_open)} of {len(opened)} connections were never closed"
    )
