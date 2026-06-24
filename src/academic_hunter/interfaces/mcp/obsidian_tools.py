import os
from datetime import datetime
from academic_hunter.core.infra.config import HunterConfig

def export_to_obsidian(topic: str, content: str, tags: list = None) -> str:
    """
    Exporta um relatório formatado em Markdown diretamente para o Vault do Obsidian do usuário.
    O caminho do Vault deve estar configurado no config.json em settings.obsidian_vault_path.
    
    Args:
        topic: O título ou tema da nota (será usado no frontmatter e no nome do arquivo).
        content: O conteúdo Markdown do relatório.
        tags: Lista opcional de tags para o Obsidian (ex: ["pesquisa", "IA"]).
    """
    try:
        config = HunterConfig()
        obsidian_path = config.settings.get("obsidian_vault_path")
        
        if not obsidian_path:
            return (
                "Erro: Caminho do Obsidian não configurado. "
                "Por favor, adicione 'obsidian_vault_path' na chave 'settings' do seu config.json."
            )
            
        if not os.path.exists(obsidian_path):
            return f"Erro: O caminho configurado para o Obsidian não existe ({obsidian_path})."
            
        # Cria a subpasta Academic_Hunter se não existir
        target_dir = os.path.join(obsidian_path, "Academic_Hunter")
        os.makedirs(target_dir, exist_ok=True)
        
        # Prepara o Frontmatter
        date_str = datetime.now().strftime("%Y-%m-%d")
        tags_str = ", ".join(tags) if tags else "academic-hunter"
        
        frontmatter = f"""---
title: "{topic}"
date: {date_str}
tags: [{tags_str}]
---
"""
        
        # Limpa o nome do arquivo
        safe_title = "".join([c if c.isalnum() else "_" for c in topic])
        filename = f"{date_str}_{safe_title}.md"
        filepath = os.path.join(target_dir, filename)
        
        # Escreve o arquivo
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(frontmatter + "\n" + content)
            
        return f"Sucesso! Relatório exportado para o Obsidian em: {filepath}"
    except Exception as e:
        return f"Erro ao exportar para o Obsidian: {str(e)}"
