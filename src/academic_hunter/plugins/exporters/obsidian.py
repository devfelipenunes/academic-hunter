"""Obsidian vault writer.

Pure file-writing logic, extracted from the MCP tool so that the pipeline can
auto-export a run without importing the interface layer. The MCP tool keeps the
presentation concerns (``ctx`` messages, error strings) and delegates the write
here.
"""

from datetime import date
from pathlib import Path
from typing import List, Optional


def write_obsidian_note(
    vault_path: str,
    topic: str,
    content: str,
    tags: Optional[List[str]] = None,
) -> Path:
    """Write a note into the ``Academic_Hunter`` folder of an Obsidian vault.

    Args:
        vault_path: Root of the Obsidian vault.
        topic: Note title, used in the frontmatter and filename.
        content: Markdown body of the note.
        tags: Obsidian tags; defaults to the Academic Hunter pair.

    Returns:
        The path the note was written to.

    Raises:
        NotADirectoryError: If ``vault_path`` does not exist.
    """
    vault = Path(vault_path)
    if not vault.exists():
        raise NotADirectoryError(f"Obsidian path does not exist ({vault_path}).")

    today = date.today().isoformat()
    tags_list = tags or ["academic-hunter", "research"]
    safe_title = "".join(c if c.isalnum() else "_" for c in topic)[:60]
    filename = f"{today}_{safe_title}.md"

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

    target_dir = vault / "Academic_Hunter"
    target_dir.mkdir(parents=True, exist_ok=True)
    filepath = target_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(frontmatter + "\n" + content)

    return filepath
