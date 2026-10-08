"""Tests for Obsidian export tool.

Uses mock_ctx from conftest and patches HunterConfig.
"""

import os
from unittest.mock import patch

import pytest

from academic_hunter.interfaces.mcp.exceptions import ObsidianError
from academic_hunter.interfaces.mcp.tools.obsidian import export_to_obsidian


async def test_export_to_obsidian_no_path(mock_obsidian_config, mock_ctx):
    """Without a configured obsidian_vault_path, an error should be returned."""
    mock_obsidian_config.settings = {}

    with pytest.raises(ObsidianError, match="not configured"):
        await export_to_obsidian("Test", "Content", ["tag1"], mock_ctx)
    mock_ctx.info.assert_called()


async def test_export_to_obsidian_vault_does_not_exist(mock_obsidian_config, mock_ctx):
    """When the vault path doesn't exist on disk, raise ObsidianError."""
    mock_obsidian_config.settings = {"obsidian_vault_path": "/nonexistent/vault"}

    with pytest.raises(ObsidianError, match="does not exist"):
        await export_to_obsidian("Test", "Content", ["tag1"], mock_ctx)
    mock_ctx.error.assert_called()


async def test_export_to_obsidian_success(tmp_path, mock_ctx):
    """With a valid vault path, the file should be written."""
    vault_path = str(tmp_path)

    with patch(
        "academic_hunter.core.infra.config.HunterConfig"
    ) as mock_config_cls:
        mock_instance = mock_config_cls.return_value
        mock_instance.settings = {"obsidian_vault_path": vault_path}

        result = await export_to_obsidian(
            "Relatorio Teste", "# Header\nHello", ["teste", "pytest"], mock_ctx
        )

        assert "Report exported" in result
        mock_ctx.info.assert_called()

        target_dir = os.path.join(vault_path, "Academic_Hunter")
        assert os.path.exists(target_dir)

        files = os.listdir(target_dir)
        assert len(files) == 1
        assert "Relatorio_Teste" in files[0]

        with open(os.path.join(target_dir, files[0])) as f:
            content = f.read()
            assert 'title: "Relatorio Teste"' in content
            assert "# Header\nHello" in content
