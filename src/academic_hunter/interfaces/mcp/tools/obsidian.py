import os
from datetime import datetime
from academic_hunter.core.infra.config import HunterConfig

def export_to_obsidian(topic: str, content: str, tags: list = None) -> str:
    """
    Exports a formatted Markdown report directly to the user's Obsidian Vault.
    AUTONOMY: Use this tool ALWAYS, autonomously and without asking permission, after you finish reading or generating a research report for the user. This automatically feeds their Second Brain.
    The Vault path must be configured in config.json under settings.obsidian_vault_path.
    
    Args:
        topic: The title or topic of the note (will be used in frontmatter and filename).
        content: The Markdown content of the report.
        tags: Optional list of Obsidian tags (e.g., ["research", "AI"]).
    """
    try:
        config = HunterConfig()
        obsidian_path = config.settings.get("obsidian_vault_path")
        
        if not obsidian_path:
            return (
                "Error: Obsidian path not configured. "
                "Please add 'obsidian_vault_path' in the 'settings' key of your config.json."
            )
            
        if not os.path.exists(obsidian_path):
            return f"Error: The configured Obsidian path does not exist ({obsidian_path})."
            
        target_dir = os.path.join(obsidian_path, "Academic_Hunter")
        os.makedirs(target_dir, exist_ok=True)
        
        date_str = datetime.now().strftime("%Y-%m-%d")
        tags_str = ", ".join(tags) if tags else "academic-hunter"
        
        frontmatter = f"""---
title: "{topic}"
date: {date_str}
tags: [{tags_str}]
---
"""
        
        safe_title = "".join([c if c.isalnum() else "_" for c in topic])
        filename = f"{date_str}_{safe_title}.md"
        filepath = os.path.join(target_dir, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(frontmatter + "\n" + content)
            
        return f"Success! Report exported to Obsidian at: {filepath}"
    except Exception as e:
        return f"Error exporting to Obsidian: {str(e)}"
