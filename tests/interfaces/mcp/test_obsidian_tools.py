import os
import json
import pytest
from unittest.mock import patch
from academic_hunter.interfaces.mcp.tools.obsidian import export_to_obsidian


def test_export_to_obsidian_no_path():
    """Without a configured obsidian_vault_path, an error should be returned."""
    with patch(
        "academic_hunter.interfaces.mcp.tools.obsidian.HunterConfig"
    ) as MockConfig:
        mock_instance = MockConfig.return_value
        mock_instance.settings = {}

        result = export_to_obsidian("Test", "Content", ["tag1"])
        assert "Error" in result
        assert "not configured" in result


def test_export_to_obsidian_success(tmp_path):
    """With a valid vault path, the file should be written."""
    vault_path = str(tmp_path)

    with patch(
        "academic_hunter.interfaces.mcp.tools.obsidian.HunterConfig"
    ) as MockConfig:
        mock_instance = MockConfig.return_value
        mock_instance.settings = {"obsidian_vault_path": vault_path}

        result = export_to_obsidian(
            "Relatorio Teste", "# Header\nHello", ["teste", "pytest"]
        )

        assert "Report exported" in result

        # Check directory and file were created
        target_dir = os.path.join(vault_path, "Academic_Hunter")
        assert os.path.exists(target_dir)

        files = os.listdir(target_dir)
        assert len(files) == 1
        assert "Relatorio_Teste" in files[0]

        with open(os.path.join(target_dir, files[0]), "r") as f:
            content = f.read()
            assert 'title: "Relatorio Teste"' in content
            assert "# Header\nHello" in content
