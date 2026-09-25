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


async def test_read_config(mock_hunter_config, mock_ctx):
    result = await read_config(mock_ctx)
    data = json.loads(result)
    assert "settings" in data
    assert data["settings"]["start_year"] == 2020
    mock_ctx.info.assert_called()


async def test_read_config_never_returns_api_keys(mock_ctx, tmp_path):
    """The config goes to the MCP client, so a credential in it would have leaked.

    Uses a real ``HunterConfig`` rather than the mock: the property only means
    something if the redaction actually runs.
    """
    from academic_hunter.core.infra.config import REDACTED, HunterConfig

    secret = "s2k-do-not-leak-this"
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "settings": {
                    "start_year": 2021,
                    "semantic_scholar_api_key": secret,
                    "api_keys": {"semantic_scholar": secret},
                },
                "anchors": {},
                "technical_strings": {},
                "technical_weights": {},
            }
        )
    )

    with patch(
        "academic_hunter.interfaces.mcp.tools.configuration.get_config",
        return_value=HunterConfig(config_path=str(path)),
    ):
        result = await read_config(mock_ctx)

    assert secret not in result, "the API key reached the MCP client"
    assert REDACTED in result, "the caller can still see that a key is configured"


async def test_read_config_failure(mock_ctx):
    with patch(
        "academic_hunter.core.infra.config.HunterConfig"
    ) as m:
        m.side_effect = RuntimeError("config.json missing")
        with pytest.raises(MCPToolError, match="config.json missing"):
            await read_config(mock_ctx)
    mock_ctx.error.assert_called()


# ── update_config ──────────────────────────────────────────────────────────────


async def test_update_config_and_history(mock_hunter_config, mock_mcp_db, mock_ctx):
    config_update = SearchConfigUpdate(
        topic="Test Topic",
        settings={"start_year": 2024},
        technical_weights={"new": 2.0},
    )
    result = await update_config(config_update, mock_ctx)
    assert "successfully" in result.lower()

    # Verify config was saved
    assert mock_hunter_config.settings["start_year"] == 2024
    assert mock_hunter_config.tech_weights["new"] == 2.0
    # Two DB saves: one "Before" backup, one final
    assert mock_mcp_db.save_config.call_count == 2
    mock_ctx.info.assert_called()


async def test_update_config_failure(mock_hunter_config, mock_mcp_db, mock_ctx):
    mock_hunter_config.save.side_effect = RuntimeError("permission denied")

    config_update = SearchConfigUpdate(topic="Fail")
    with pytest.raises(MCPToolError, match="permission denied"):
        await update_config(config_update, mock_ctx)
    mock_ctx.error.assert_called()


# ── list_config_history ────────────────────────────────────────────────────────


async def test_list_config_history(mock_mcp_db, mock_ctx):
    result = await list_config_history(mock_ctx)
    assert "Backup 1" in result
    mock_ctx.info.assert_called()


async def test_list_config_history_empty(mock_mcp_db, mock_ctx):
    mock_mcp_db.list_configs.return_value = []
    result = await list_config_history(mock_ctx)
    assert "No configuration history" in result
    mock_ctx.info.assert_called()


async def test_list_config_history_failure(mock_mcp_db, mock_ctx):
    mock_mcp_db.list_configs.side_effect = RuntimeError("DB error")
    with pytest.raises(MCPToolError, match="DB error"):
        await list_config_history(mock_ctx)
    mock_ctx.error.assert_called()


# ── restore_config_by_id ──────────────────────────────────────────────────────


async def test_restore_config_by_id(mock_hunter_config, mock_mcp_db, mock_ctx):
    mock_mcp_db.get_config.return_value = {
        "settings": {"start_year": 1999},
        "anchors": {},
        "tech_strings": {},
        "tech_weights": {"old": 1.0},
        "context_rules": {},
        "keyword_only_terms": [],
        "keyword_only_category": "",
    }

    result = await restore_config_by_id(1, mock_ctx)
    assert "restored" in result.lower()
    assert mock_hunter_config.settings["start_year"] == 1999
    mock_ctx.info.assert_called()


async def test_restore_config_by_id_not_found(mock_mcp_db, mock_ctx):
    mock_mcp_db.get_config.return_value = None
    with pytest.raises(MCPToolError, match="Config ID 1 not found"):
        await restore_config_by_id(1, mock_ctx)
    mock_ctx.error.assert_called()


async def test_restore_config_by_id_failure(mock_hunter_config, mock_mcp_db, mock_ctx):
    mock_mcp_db.get_config.side_effect = RuntimeError("DB crash")
    with pytest.raises(MCPToolError, match="DB crash"):
        await restore_config_by_id(1, mock_ctx)
    mock_ctx.error.assert_called()


async def test_the_backup_does_not_store_credentials(mock_ctx, tmp_path):
    """The history is plain text in SQLite; a config backup is not a key store."""
    from academic_hunter.core.infra.config import REDACTED, HunterConfig

    secret = "s2k-must-not-reach-the-db"
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "settings": {
                    "start_year": 2021,
                    "semantic_scholar_api_key": secret,
                    "api_keys": {"semantic_scholar": secret},
                },
                "anchors": {},
                "technical_strings": {},
                "technical_weights": {},
            }
        )
    )
    real_config = HunterConfig(config_path=str(path))

    with (
        patch(
            "academic_hunter.interfaces.mcp.tools.configuration.get_config",
            return_value=real_config,
        ),
        patch(
            "academic_hunter.interfaces.mcp.tools.configuration.MCPDatabaseManager"
        ) as m_db,
    ):
        m_db.return_value.save_config.return_value = None
        await update_config(
            SearchConfigUpdate(topic="T", settings={"start_year": 2022}), mock_ctx
        )

    saved = [call.kwargs["config_data"] for call in m_db.return_value.save_config.call_args_list]
    assert saved, "nothing was backed up"
    for snapshot in saved:
        dumped = json.dumps(snapshot)
        assert secret not in dumped, f"the key reached the SQLite history: {dumped}"
        assert REDACTED in dumped, "the snapshot should still show a key is set"


# ── limpar versus não mencionar ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "field, attribute",
    [("anchors", "anchors"), ("technical_strings", "tech_strings"),
     ("technical_weights", "tech_weights")],
)
async def test_an_empty_mapping_clears_what_was_there(
    mock_hunter_config, mock_mcp_db, mock_ctx, field, attribute
):
    """`if config_update.anchors:` is falsy for `{}`.

    A researcher could replace the anchors but never remove them: the call
    reported success and the old ones stayed. An omitted field and an empty one
    are different requests — "do not touch" and "make it empty" — and only
    `is not None` can tell them apart, since the schema defaults to `None`.
    """
    setattr(mock_hunter_config, attribute, {"Old": ["term"]})

    await update_config(SearchConfigUpdate(topic="Clear", **{field: {}}), mock_ctx)

    assert getattr(mock_hunter_config, attribute) == {}, (
        f"{field} was not cleared"
    )


async def test_an_omitted_mapping_is_left_alone(mock_hunter_config, mock_mcp_db, mock_ctx):
    """The other half: not mentioning a field must not wipe it."""
    mock_hunter_config.anchors = {"Kept": ["term"]}

    await update_config(SearchConfigUpdate(topic="Only the topic"), mock_ctx)

    assert mock_hunter_config.anchors == {"Kept": ["term"]}


async def test_restoring_removes_what_was_added_after_the_backup(
    mock_hunter_config, mock_mcp_db, mock_ctx
):
    """The backup's settings were **merged** over the current ones.

    A key added after the backup survived the restore, so "restore this
    configuration" returned a hybrid of the two and the researcher could not get
    back to the state they had saved. The live credentials are the one thing that
    must survive — a backup never carries them.
    """
    mock_hunter_config.settings = {"start_year": 2024, "rerank": {"enabled": True}}
    mock_mcp_db.get_config.return_value = {"settings": {"start_year": 1999}}

    await restore_config_by_id(1, mock_ctx)

    assert mock_hunter_config.settings["start_year"] == 1999
    assert "rerank" not in mock_hunter_config.settings, (
        "a setting added after the backup survived the restore"
    )


# ── o que a configuração vai consultar ─────────────────────────────────────


async def _apply(config_update, mock_ctx, tmp_path, initial):
    from academic_hunter.core.infra.config import HunterConfig

    path = tmp_path / "config.json"
    path.write_text(json.dumps(initial), encoding="utf-8")

    with (
        patch(
            "academic_hunter.interfaces.mcp.tools.configuration.get_config",
            return_value=HunterConfig(config_path=str(path)),
        ),
        patch("academic_hunter.interfaces.mcp.tools.configuration.MCPDatabaseManager") as m_db,
    ):
        m_db.return_value.save_config.return_value = None
        return await update_config(config_update, mock_ctx)


async def test_update_config_names_the_sources_an_empty_technical_strings_skips(mock_ctx, tmp_path):
    """Anchors alone leave four of the six sources unqueried, and the reply said
    nothing about it.

    The call answered "successfully", the run that followed searched two sources
    of six, and the missing four reported 0 as though they had been asked and
    found nothing. Naming them here is what makes it visible before the run.
    """
    result = await _apply(
        SearchConfigUpdate(topic="CBDC", anchors={"Topic": ["central bank digital currency"]}),
        mock_ctx,
        tmp_path,
        {"settings": {}, "anchors": {}, "technical_strings": {}},
    )

    assert "successfully" in result.lower()
    assert "will NOT be queried" in result
    assert "technical_strings" in result
    for grid_source in ("ArXiv", "Crossref", "OpenAlex", "CORE"):
        assert grid_source in result, f"{grid_source} was not named as skipped"


async def test_update_config_counts_the_queries_a_complete_config_will_run(mock_ctx, tmp_path):
    """One anchor x two technical categories is two grid queries, and no warning."""
    result = await _apply(
        SearchConfigUpdate(
            topic="CBDC",
            anchors={"Topic": ["cbdc"]},
            technical_strings={"Ledger": ["distributed ledger"], "Policy": ["monetary policy"]},
        ),
        mock_ctx,
        tmp_path,
        {"settings": {}, "anchors": {}, "technical_strings": {}},
    )

    assert "2 queries" in result
    assert "will NOT be queried" not in result


async def test_update_config_says_when_the_config_will_query_nothing(mock_ctx, tmp_path):
    """Weights with no anchors are not a searchable config, and `run_search`
    would refuse. Saying so here is cheaper than the refusal later."""
    result = await _apply(
        SearchConfigUpdate(topic="CBDC", technical_weights={"iso 20022": 2.0}),
        mock_ctx,
        tmp_path,
        {"settings": {}, "anchors": {}, "technical_weights": {}},
    )

    assert "Query nothing" in result
    assert "anchors" in result


async def test_read_config_says_which_file_it_read(mock_ctx, tmp_path, monkeypatch):
    """The search order is environment-dependent, so the caller has to be told
    which rung won — otherwise "my config is being ignored" has no answer, and
    the packaged default looks like a config someone chose, only an empty one."""
    from academic_hunter.core.infra import paths
    from academic_hunter.core.infra.config import HunterConfig

    target = tmp_path / paths.CONFIG_FILENAME
    target.write_text(
        json.dumps({"settings": {"start_year": 2016}, "anchors": {"T": ["x"]}}),
        encoding="utf-8",
    )
    monkeypatch.setenv(paths.CONFIG_ENV, str(target))

    with patch(
        "academic_hunter.interfaces.mcp.tools.configuration.get_config",
        side_effect=HunterConfig,
    ):
        data = json.loads(await read_config(mock_ctx))

    assert data["config_source"]["path"] == str(target)
    assert data["config_source"]["origin"] == paths.ORIGIN_ENV
    assert data["config_source"]["is_default"] is False
    assert data["settings"]["start_year"] == 2016


async def test_read_config_flags_the_packaged_default(mock_ctx, tmp_path, monkeypatch):
    from academic_hunter.core.infra import paths
    from academic_hunter.core.infra.config import HunterConfig

    monkeypatch.setattr(paths, "checkout_root", lambda: None)
    for name in (paths.CONFIG_ENV, paths.DATA_ENV, paths.PROJECT_ENV, "XDG_CONFIG_HOME"):
        monkeypatch.delenv(name, raising=False)
    neutral = tmp_path / "neutral"
    neutral.mkdir()
    monkeypatch.chdir(neutral)

    with patch(
        "academic_hunter.interfaces.mcp.tools.configuration.get_config",
        side_effect=HunterConfig,
    ):
        data = json.loads(await read_config(mock_ctx))

    assert data["config_source"]["is_default"] is True
    assert data["config_source"]["origin"] == paths.ORIGIN_PACKAGED
