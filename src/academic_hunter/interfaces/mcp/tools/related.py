"""MCP tool for semantically similar paper search.

Accepts a ``ctx: Context`` parameter (auto-injected by FastMCP)
for logging and progress reporting.
"""

import logging

from mcp.server.fastmcp import Context

from ._utils import _get_vector_store

logger = logging.getLogger("academic_hunter.mcp.related")


async def find_related_papers(ctx: Context, query: str, top_k: int = 20) -> str:
    """Finds papers semantically similar to a given query.

    Args:
        ctx: FastMCP Context (auto-injected).
        query: Search text (title, DOI, or free text).
        top_k: Number of results (default 5, max 20).
    """
    await ctx.info(f"Finding papers related to: '{query[:60]}'...")
    store = _get_vector_store()
    if store is None:
        await ctx.error("Vector store not available")
        return "Vector store not available. Index papers first."

    top_k = min(top_k, 20)
    results = store.query(query, top_k=top_k)
    if not results:
        await ctx.info("No related papers found")
        return "No related papers found. Try a different query."

    lines = ["# Related Papers\n", f"**Query:** {query}\n",
             f"**Results:** {len(results)}\n", "---\n"]
    for i, paper in enumerate(results, 1):
        title = paper.get("title", "Untitled")
        rel = paper.get("semantic_relevance", 0)
        year = paper.get("year", "?")
        doi = paper.get("doi", "")
        preview = paper.get("abstract_preview", "")
        lines.append(f"## {i}. {title}\n")
        lines.append(f"- **Relevance:** {rel:.1%} | **Year:** {year}\n")
        if doi: lines.append(f"- **DOI:** `{doi}`\n")
        if preview: lines.append(f"{preview[:200]}...\n")
        lines.append("")
    await ctx.info(f"Found {len(results)} related papers")
    return "\n".join(lines)
