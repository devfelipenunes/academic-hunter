"""MCP tool for searching bioRxiv/medRxiv preprints (life sciences, medicine).

bioRxiv (https://api.biorxiv.org/) provides metadata for 260K+ life science
preprints.  medRxiv shares the same API at a different endpoint.
No API key is needed.
"""

import logging
from datetime import datetime, timedelta

import requests
from mcp.server.fastmcp import Context

from ..exceptions import DiscoveryError

logger = logging.getLogger("academic_hunter.mcp.biorxiv")

BIORXIV_API = "https://api.biorxiv.org/details/biorxiv"
MEDRXIV_API = "https://api.biorxiv.org/details/medrxiv"

# Common bioRxiv subject categories (for reference / hinting)



async def search_biorxiv(
    ctx: Context, query: str, server: str = "bio", limit: int = 10
) -> str:
    """Searches bioRxiv or medRxiv for recent preprints.

    bioRxiv: life sciences (260K+ preprints)
    medRxiv: health sciences (medicine, epidemiology, clinical research)

    Because the bioRxiv API returns papers by date range (not by keyword),
    we fetch recent preprints and filter client-side by title/abstract.

    Args:
        ctx: FastMCP Context (auto-injected).
        query: Search term (matched against title and abstract).
        server: ``"bio"`` for bioRxiv (default) or ``"med"`` for medRxiv.
        limit: Maximum number of results to return (default 10).
    """
    await ctx.info(f"Searching {server}Rxiv for: '{query}'...")

    if server.lower() not in ("bio", "med"):
        await ctx.error(f"Invalid server: {server}")
        return "Server must be 'bio' or 'med'."

    api_url = BIORXIV_API if server.lower() == "bio" else MEDRXIV_API
    server_name = "bioRxiv" if server.lower() == "bio" else "medRxiv"

    try:
        # bioRxiv API is date-range / cursor-based.  Fetch recent papers
        # and filter by keyword client-side.
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")

        # Request more than ``limit`` to leave room for client-side filtering.
        # The API cursor parameter is ``{start}/{end}/{cursor}/{count}``.
        url = f"{api_url}/{start_date}/{end_date}/0/{limit * 3}"

        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        collection = data.get("collection", [])
        if not collection:
            await ctx.info(f"No recent preprints found for '{query}'")
            return f"No preprints found for: '{query}'."

        # Client-side keyword filter on title and abstract
        query_lower = query.lower()
        matches = []
        for preprint in collection:
            title = preprint.get("title", "")
            abstract = preprint.get("abstract", "")
            if query_lower in title.lower() or query_lower in abstract.lower():
                matches.append(preprint)

        matches = matches[:limit]

        if not matches:
            await ctx.info(f"No matching preprints for '{query}'")
            return f"No matching preprints found for: '{query}'."

        lines = [
            f"# {server_name} Preprints: {query}\n",
            f"**Results:** {len(matches)}\n",
            "---\n",
        ]

        for i, p in enumerate(matches, 1):
            title = p.get("title", "Untitled")
            authors = p.get("authors", "?")
            doi = p.get("doi", "")
            date = p.get("date", "?")
            category = p.get("category", "")
            abstract = p.get("abstract", "")

            lines.append(f"## {i}. {title}\n")
            lines.append(f"- **Authors:** {authors}\n")
            lines.append(f"- **Date:** {date} | **Category:** {category}\n")
            if doi:
                lines.append(f"- **DOI:** `{doi}`\n")
            if abstract:
                lines.append(f"- **Abstract:** {abstract[:200]}...\n")
            lines.append("")

        await ctx.info(f"Found {len(matches)} preprints on {server_name}")
        return "\n".join(lines)

    except Exception as e:
        await ctx.error(f"{server_name} search failed: {e}")
        raise DiscoveryError(str(e))
