"""MCP tool for searching OpenAIRE Graph — publications linked to grants and funding.

OpenAIRE indexes 198M+ publications and links them to 3.7M+ grants
from 203 funders (EU, NSF, etc.).  Free tier: 60 req/hr without token,
7 200 req/hr with a free token.
"""

import logging
import requests
from mcp.server.fastmcp import Context
from ..exceptions import DiscoveryError

logger = logging.getLogger("academic_hunter.mcp.openaire")
OPENAIRE_API = "https://api.openaire.eu"


async def search_openaire(ctx: Context, query: str, limit: int = 10) -> str:
    """Searches OpenAIRE for publications linked to research grants and funding.

    OpenAIRE indexes 198M+ publications and links them to 3.7M+ grants
    from 203 funders (EU, NSF, etc.).

    Args:
        ctx: FastMCP Context (auto-injected).
        query: Search query.
        limit: Max results (default 10, max 50).
    """
    await ctx.info(f"Searching OpenAIRE for: '{query}'...")
    try:
        params = {
            "query": query,
            "size": min(limit, 50),
            "format": "json",
        }
        url = f"{OPENAIRE_API}/graph/publications"
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("response", {}).get("results", [])

        if not results:
            await ctx.info(f"No OpenAIRE results for '{query}'")
            return f"No results found for: '{query}'."

        lines = [f"# OpenAIRE Results: {query}\n", f"**Total:** {len(results)}\n", "---\n"]
        for i, result in enumerate(results[:limit], 1):
            metadata = result.get("metadata", {})
            pid = metadata.get("pid", "")
            title = metadata.get("title", "Untitled")
            creators = metadata.get("creator", "?")
            if isinstance(creators, list):
                creators = "; ".join(creators[:4])
            pub_date = metadata.get("publicationDate", "?")
            funding = metadata.get("fundingReference", [])
            funder = funding[0].get("funderName", "") if funding else ""
            oa = "✅ OA" if metadata.get("isOpenAccess") else ""

            lines.append(f"## {i}. {title} {oa}\n")
            lines.append(f"- **Authors:** {creators}\n")
            lines.append(f"- **Date:** {pub_date}\n")
            if funder:
                lines.append(f"- **Funder:** {funder}\n")
            if pid:
                lines.append(f"- **PID:** {pid}\n")
            lines.append("")

        await ctx.info(f"Found {len(results)} OpenAIRE results")
        return "\n".join(lines)

    except Exception as e:
        await ctx.error(f"OpenAIRE search failed: {e}")
        raise DiscoveryError(str(e))
