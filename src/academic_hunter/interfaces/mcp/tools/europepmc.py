"""MCP tools for Europe PMC search — life sciences literature, preprints, full-text.

Europe PMC (https://europepmc.org/) indexes 42M+ abstracts and 9M+ full-text
articles, including preprints from bioRxiv, medRxiv, and ChemRxiv.
No API key is required.
"""

import asyncio
import requests
from mcp.server.fastmcp import Context
from ..exceptions import DiscoveryError


async def search_europepmc(ctx: Context, query: str, limit: int = 10) -> str:
    """Searches Europe PMC for life sciences and biomedical literature.

    Europe PMC indexes 42M+ abstracts and 9M+ full-text articles,
    including preprints from bioRxiv, medRxiv, and ChemRxiv.

    Args:
        ctx: FastMCP Context (auto-injected).
        query: Search query (supports Europe PMC query syntax).
        limit: Max results (default 10, max 50).
    """
    await ctx.info(f"Searching Europe PMC for: '{query}'...")

    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {
        "query": query,
        "pageSize": min(limit, 50),
        "format": "json",
        "resultType": "core",
    }

    try:
        resp = await asyncio.to_thread(requests.get, url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        results = data.get("resultList", {}).get("result", [])

        if not results:
            await ctx.info("No results found")
            return f"No results found for: '{query}'."

        lines = [
            f"# Europe PMC Results: {query}\n",
            f"**Total results:** {data.get('hitCount', 0)}\n",
            "---\n",
        ]

        for i, paper in enumerate(results[:limit], 1):
            title = paper.get("title", "Untitled")
            authors_list = paper.get("authorString", "")
            year = paper.get("firstPublicationDate", "?")[:4] if paper.get("firstPublicationDate") else "?"
            doi = paper.get("doi", "")
            source = paper.get("source", "")
            is_open_access = paper.get("isOpenAccess", False)
            preprint = "[PREPRINT]" if "preprint" in source.lower() else ""
            oa = "[OA]" if is_open_access else ""

            lines.append(f"## {i}. {title} {preprint} {oa}\n")
            lines.append(f"- **Authors:** {authors_list}\n")
            lines.append(f"- **Year:** {year} | **Source:** {source}\n")
            if doi:
                lines.append(f"- **DOI:** `{doi}`\n")
            if paper.get("abstractText"):
                abstract = paper["abstractText"][:300]
                lines.append(f"- **Abstract:** {abstract}...\n")
            lines.append("")

        await ctx.info(f"Found {len(results)} results from Europe PMC")
        return "\n".join(lines)

    except Exception as e:
        await ctx.error(f"Europe PMC search failed: {e}")
        raise DiscoveryError(str(e))
