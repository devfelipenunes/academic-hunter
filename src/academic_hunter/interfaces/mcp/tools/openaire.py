"""MCP tool for searching OpenAIRE Graph.

Indexes 198M+ publications linked to 3.7M+ grants.
"""

import asyncio
import logging
import requests
from mcp.server.fastmcp import Context
from ..exceptions import DiscoveryError

logger = logging.getLogger("academic_hunter.mcp.openaire")


def _extract_meta(oaf: dict) -> dict:
    """Extract flat metadata from OpenAIRE's nested oaf:result structure."""
    title_list = oaf.get("title", [])
    title = ""
    for t in title_list:
        if t.get("@classid") == "main title":
            title = t.get("$", "")
            break
    if not title and title_list:
        title = title_list[0].get("$", "")

    creators = oaf.get("creator", [])
    authors = "; ".join(c.get("$", "") for c in creators[:5]) if creators else "?"

    date_acc = oaf.get("dateofacceptance", {})
    pub_date = date_acc.get("$", "?")[:10] if isinstance(date_acc, dict) else "?"

    pids = oaf.get("pid", [])
    doi = ""
    for p in pids:
        if p.get("@classid") == "doi":
            doi = p.get("$", "")
            break

    access = oaf.get("bestaccessright", {})
    is_oa = "✅ OA" if access.get("@classid") == "OPEN ACCESS" else ""

    projects = oaf.get("project", [])
    funder = ""
    if isinstance(projects, dict):
        projects = [projects]
    for proj in projects[:3]:
        fn = proj.get("funder", {})
        if isinstance(fn, dict):
            fname = fn.get("$", "") or fn.get("@classname", "")
            if fname:
                funder = fname

    return {"title": title, "authors": authors, "date": pub_date, "doi": doi, "oa": is_oa, "funder": funder}


async def search_openaire(ctx: Context, query: str, limit: int = 10) -> str:
    """Searches OpenAIRE for publications linked to research grants and funding.

    Args:
        ctx: FastMCP Context (auto-injected).
        query: Search query.
        limit: Max results (default 10, max 50).
    """
    await ctx.info(f"Searching OpenAIRE for: '{query}'...")
    try:
        params = {"keywords": query, "size": min(limit, 50), "format": "json"}
        resp = await asyncio.to_thread(requests.get, "https://api.openaire.eu/search/publications", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        results_container = data.get("response", {}).get("results", {}) or {}
        result_list = results_container.get("result", []) if isinstance(results_container, dict) else results_container or []
        if not result_list:
            await ctx.info(f"No OpenAIRE results for '{query}'")
            return f"No results found for: '{query}'."

        lines = [f"# OpenAIRE Results: {query}\n", f"**Total:** {len(result_list)}\n", "---\n"]
        for i, r in enumerate(result_list[:limit], 1):
            oaf = r.get("metadata", {}).get("oaf:entity", {}).get("oaf:result", {})
            meta = _extract_meta(oaf)
            title = meta["title"] or "Untitled"
            lines.append(f"## {i}. {title} {meta['oa']}\n")
            lines.append(f"- **Authors:** {meta['authors']}\n")
            lines.append(f"- **Date:** {meta['date']}\n")
            if meta["funder"]: lines.append(f"- **Funder:** {meta['funder']}\n")
            if meta["doi"]: lines.append(f"- **DOI:** `{meta['doi']}`\n")
            lines.append("")

        await ctx.info(f"Found {len(result_list)} OpenAIRE results")
        return "\n".join(lines)
    except Exception as e:
        await ctx.error(f"OpenAIRE search failed: {e}")
        raise DiscoveryError(str(e))
