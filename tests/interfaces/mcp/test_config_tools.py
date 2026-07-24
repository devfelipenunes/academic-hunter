"""Tests for configuration MCP tools (read_config, update_config, list_config_history, restore_config_by_id).

Uses mock_ctx from conftest and patches HunterConfig and MCPDatabaseManager.
"""

import json
import pytest
from unittest.mock import patch

from academic_hunter.interfaces.mcp.tools.configuration import (
    read_config,
    update_config,
    list_config_history,
    restore_config_by_id,
)
from academic_hunter.interfaces.mcp.schemas.config_schema import SearchConfigUpdate
from academic_hunter.interfaces.mcp.exceptions import MCPToolError


# ── read_config ────────────────────────────────────────────────────────────────


def test_read_config(mock_hunter_config, mock_ctx):
    result = read_config(mock_ctx)
    data = json.loads(result)
    assert "settings" in data
    assert data["settings"]["start_year"] == 2020
    mock_ctx.info.assert_called()


def test_read_config_failure(mock_ctx):
    with patch(
        "academic_hunter.interfaces.mcp.tools.configuration.HunterConfig"
    ) as m:
        m.side_effect = RuntimeError("config.json missing")
        with pytest.raises(MCPToolError, match="config.json missing"):
            read_config(mock_ctx)
    mock_ctx.error.assert_called()


# ── update_config ──────────────────────────────────────────────────────────────


def test_update_config_and_history(mock_hunter_config, mock_mcp_db, mock_ctx):
    config_update = SearchConfigUpdate(
        topic="Test Topic",
        settings={"start_year": 2024},
        technical_weights={"new": 2.0},
    )
    result = update_config(config_update, mock_ctx)
    assert "successfully" in result.lower()

    # Verify config was saved
    assert mock_hunter_config.settings["start_year"] == 2024
    assert mock_hunter_config.tech_weights["new"] == 2.0
    # Two DB saves: one "Before" backup, one final
    assert mock_mcp_db.save_config.call_count == 2
    mock_ctx.info.assert_called()


def test_update_config_failure(mock_hunter_config, mock_mcp_db, mock_ctx):
    mock_hunter_config.save.side_effect = RuntimeError("permission denied")

    config_update = SearchConfigUpdate(topic="Fail")
    with pytest.raises(MCPToolError, match="permission denied"):
        update_config(config_update, mock_ctx)
    mock_ctx.error.assert_called()


# ── list_config_history ────────────────────────────────────────────────────────


def test_list_config_history(mock_mcp_db, mock_ctx):
    result = list_config_history(mock_ctx)
    assert "Backup 1" in result
    mock_ctx.info.assert_called()


def test_list_config_history_empty(mock_mcp_db, mock_ctx):
    mock_mcp_db.list_configs.return_value = []
    result = list_config_history(mock_ctx)
    assert "No configuration history" in result
    mock_ctx.info.assert_called()


def test_list_config_history_failure(mock_mcp_db, mock_ctx):
    mock_mcp_db.list_configs.side_effect = RuntimeError("DB error")
    with pytest.raises(MCPToolError, match="DB error"):
        list_config_history(mock_ctx)
    mock_ctx.error.assert_called()


# ── restore_config_by_id ──────────────────────────────────────────────────────


def test_restore_config_by_id(mock_hunter_config, mock_mcp_db, mock_ctx):
    mock_mcp_db.get_config.return_value = {
        "settings": {"start_year": 1999},
        "anchors": {},
        "tech_strings": {},
        "tech_weights": {"old": 1.0},
        "context_rules": {},
        "keyword_only_terms": [],
        "keyword_only_category": "",
    }

    result = restore_config_by_id(1, mock_ctx)
    assert "restored" in result.lower()
    assert mock_hunter_config.settings["start_year"] == 1999
    mock_ctx.info.assert_called()


def test_restore_config_by_id_not_found(mock_mcp_db, mock_ctx):
    mock_mcp_db.get_config.return_value = None
    with pytest.raises(MCPToolError, match="Config ID 1 not found"):
        restore_config_by_id(1, mock_ctx)
    mock_ctx.error.assert_called()


def test_restore_config_by_id_failure(mock_hunter_config, mock_mcp_db, mock_ctx):
    mock_mcp_db.get_config.side_effect = RuntimeError("DB crash")
    with pytest.raises(MCPToolError, match="DB crash"):
        restore_config_by_id(1, mock_ctx)
    mock_ctx.error.assert_called()
