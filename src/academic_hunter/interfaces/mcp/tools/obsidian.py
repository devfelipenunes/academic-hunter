"""MCP tool to export research reports directly to the user's Obsidian vault."""

from pathlib import Path
from academic_hunter.core import get_config
from academic_hunter.plugins.exporters.obsidian import write_obsidian_note
from ..exceptions import ObsidianError
from mcp.server.fastmcp import Context


async def export_to_obsidian(topic: str, content: str, tags: list = None, ctx: Context = None) -> str:
    """Exports a formatted Markdown report directly to the user's Obsidian Vault.

    Use it when the user asks for a note to be saved, or agrees to it. Where a
    note lands is the user's knowledge base, not the tool's to decide.

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

        if not Path(obsidian_path).exists():
            await ctx.error(f"Obsidian vault path does not exist: {obsidian_path}")
            return f"Error: Obsidian path does not exist ({obsidian_path})."

        filepath = write_obsidian_note(
            vault_path=obsidian_path, topic=topic, content=content, tags=tags
        )

        await ctx.info(f"Report exported to {filepath}")
        return f"✅ Report exported to Obsidian: {filepath}"

    except ObsidianError:
        raise
    except Exception as e:
        await ctx.error(f"Failed to export to Obsidian: {e}")
        raise ObsidianError(str(e))
