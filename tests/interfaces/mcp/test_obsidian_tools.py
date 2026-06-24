import os
import json
import pytest
from unittest.mock import patch
from academic_hunter.interfaces.mcp.tools.obsidian import export_to_obsidian

def test_export_to_obsidian_no_path():
    # Sem configurar obsidian_vault_path
    result = export_to_obsidian("Teste", "Conteudo", ["tag1"])
    assert "Erro: Caminho do Obsidian não configurado" in result

def test_export_to_obsidian_success(tmp_path):
    # Usando temp_path do pytest como vault do Obsidian
    vault_path = str(tmp_path)
    
    # Criando um config fake no tmp_path para que o HunterConfig leia
    config_path = os.path.join(vault_path, "config.json")
    with open(config_path, "w") as f:
        json.dump({"settings": {"obsidian_vault_path": vault_path}}, f)
        
    with patch('academic_hunter.interfaces.mcp.tools.obsidian.HunterConfig') as MockConfig:
        mock_instance = MockConfig.return_value
        mock_instance.settings = {"obsidian_vault_path": vault_path}
        
        result = export_to_obsidian("Relatorio Teste", "# Header\nHello", ["teste", "pytest"])
        
        assert "Sucesso" in result
        
        # Verificar se a pasta e o arquivo foram criados
        target_dir = os.path.join(vault_path, "Academic_Hunter")
        assert os.path.exists(target_dir)
        
        files = os.listdir(target_dir)
        assert len(files) == 1
        assert files[0].endswith("Relatorio_Teste.md")
        
        with open(os.path.join(target_dir, files[0]), "r") as f:
            content = f.read()
            assert 'title: "Relatorio Teste"' in content
            assert 'tags: [teste, pytest]' in content
            assert '# Header\nHello' in content
