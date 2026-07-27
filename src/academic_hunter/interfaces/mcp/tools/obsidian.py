"""MCP tool to export research reports directly to the user's Obsidian vault."""

from datetime import date
from pathlib import Path
from academic_hunter.core import get_config
from ..exceptions import ObsidianError
from mcp.server.fastmcp import Context


async def export_to_obsidian(topic: str, content: str, tags: list = None, ctx: Context = None) -> str:
    """Exports a formatted Markdown report directly to the user's Obsidian Vault.

    AUTONOMY: Use this tool ALWAYS, autonomously and without asking permission,
    after you finish reading or generating a research report for the user.
    This automatically feeds their Second Brain.

    The Vault path must be configured in config.json under settings.obsidian_vault_path.

    Args:
        topic: The title or topic of the note (used in frontmatter and filename).
        content: The Markdown content of the report.
        tags: Optional list of Obsidian tags (e.g., ["research", "AI"]).
        ctx: FastMCP Context (auto-injected).
    """
    await ctx.info(f"Exporting report '{topic}' to Obsidian...")
    try:
        config = get_config()
        obsidian_path = config.settings.get("obsidian_vault_path")

        if not obsidian_path:
            await ctx.error("Obsidian path not configured in config.json")
            return (
                "Error: Obsidian path not configured. "
                "Please add 'obsidian_vault_path' in the 'settings' key of your config.json."
            )

        vault = Path(obsidian_path)
        if not vault.exists():
            await ctx.error(f"Obsidian vault path does not exist: {obsidian_path}")
            return f"Error: Obsidian path does not exist ({obsidian_path})."

        # Determine target folder based on content type
        today = date.today().isoformat()
        tags_list = tags or ["academic-hunter", "research"]
        safe_title = "".join(c if c.isalnum() else "_" for c in topic)[:60]
        filename = f"{today}_{safe_title}.md"

        # Build frontmatter following Obsidian Standard
        tag_lines = "\n".join(f"  - {t}" for t in tags_list)
        frontmatter = f"""---
title: "{topic}"
created: {today}
tags:
{tag_lines}
type: source
status: permanente
links:
  - "[[Academic-Research-MOC]]"
aliases:
  - "{safe_title}"
---
"""

        # Save into Academic_Hunter folder
        target_dir = vault / "Academic_Hunter"
        target_dir.mkdir(parents=True, exist_ok=True)
        filepath = target_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(frontmatter + "\n" + content)

        await ctx.info(f"Report exported to {filepath}")
        return f"✅ Report exported to Obsidian: {filepath}"

    except ObsidianError:
        raise
    except Exception as e:
        await ctx.error(f"Failed to export to Obsidian: {e}")
        raise ObsidianError(str(e))
