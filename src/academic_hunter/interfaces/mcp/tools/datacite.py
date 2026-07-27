"""MCP tool for searching datasets and software via DataCite API.
"""

import logging

import requests
from mcp.server.fastmcp import Context

from ..exceptions import DiscoveryError

logger = logging.getLogger("academic_hunter.mcp.datacite")
DATACITE_API = "https://api.datacite.org/dois"


async def search_datasets(
    ctx: Context, query: str, limit: int = 10, resource_type: str = ""
) -> str:
    """Searches for datasets, software, and research outputs via DataCite.

    DataCite indexes DOIs from Zenodo, Figshare, Dryad, and 1000+ repositories.

    Args:
        ctx: FastMCP Context (auto-injected).
        query: Search term.
        limit: Max results (default 10, max 50).
        resource_type: Filter by type: "dataset", "software", "text", etc.
            Empty string means all types.

    Returns:
        A Markdown-formatted list of matching DOIs with metadata.
    """
    await ctx.info(f"Searching DataCite for: '{query}'...")

    try:
        params = {
            "query": query,
            "page[size]": min(limit, 50),
            "sort": "publicationYear desc,updated desc",
        }
        if resource_type:
            params["resource-type-id"] = resource_type

        resp = requests.get(DATACITE_API, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("data", [])

        if not results:
            await ctx.info(f"No DataCite results for '{query}'")
            return f"No results found for: '{query}'."

        lines = [f"# DataCite Results: {query}\n", f"**Total:** {len(results)}\n", "---\n"]

        for i, item in enumerate(results[:limit], 1):
            attrs = item.get("attributes", {})
            title = (attrs.get("titles") or [{}])[0].get("title", "Untitled")
            creators = attrs.get("creators", [])
            author_str = "; ".join(c.get("name", "") for c in creators[:4]) or "?"
            year = attrs.get("publicationYear", "?")
            doi = attrs.get("doi", "")
            type_name = attrs.get("resourceTypeGeneral", "")
            publisher = attrs.get("publisher", "")
            rel_id = attrs.get("relatedIdentifiers", [])
            rel_str = f" (related to {len(rel_id)} DOIs)" if rel_id else ""

            lines.append(f"## {i}. {title}\n")
            lines.append(f"- **Type:** {type_name} | **Year:** {year}\n")
            lines.append(f"- **Authors:** {author_str}\n")
            if doi:
                lines.append(f"- **DOI:** `{doi}`\n")
            if publisher:
                lines.append(f"- **Publisher:** {publisher}\n")
            if rel_str:
                lines.append(f"- {rel_str}\n")
            lines.append("")

        await ctx.info(f"Found {len(results)} DataCite results")
        return "\n".join(lines)

    except requests.RequestException as e:
        await ctx.error(f"DataCite API error: {e}")
        raise DiscoveryError(str(e))
    except Exception as e:
        await ctx.error(f"DataCite search failed: {e}")
        raise DiscoveryError(str(e))
