"""MCP tool for patent search via Lens.org API.

Lens.org links 150M+ patents to academic papers.
Free tier: 1,000 requests/day with token.
"""

import logging

import asyncio
import requests
from mcp.server.fastmcp import Context

from ..exceptions import DiscoveryError

logger = logging.getLogger("academic_hunter.mcp.lens")


async def search_patents(ctx: Context, query: str, limit: int = 10) -> str:
    """Searches patents related to a research topic via Lens.org.

    Args:
        ctx: FastMCP Context (auto-injected).
        query: Search query (e.g., "blockchain consensus").
        limit: Max results (default 10, max 25).
    """
    await ctx.info(f"Searching patents for: '{query}'...")

    # Checked before the call, not after: without it every request is a 401, and
    # a 401 does not tell anyone which variable to set.
    token = _api_token()
    if not token:
        await ctx.error("Lens.org token is not configured")
        raise DiscoveryError(
            "Lens.org requires a token. Set LENS_API_KEY in the environment or "
            "settings.api_keys.lens in config.json."
        )

    try:
        url = "https://api.lens.org/patent/search"
        payload = {
            "query": {"terms": [{"field": "title", "value": query}]},
            "size": min(limit, 25),
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        resp = await asyncio.to_thread(requests.post, url, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        patents = data.get("data", [])
        if not patents:
            await ctx.info(f"No patents found for '{query}'")
            return f"No patents found for: '{query}'."

        lines = [
            f"# Patent Search: {query}\n",
            f"**Results:** {len(patents)}\n",
            "---\n",
        ]
        for i, p in enumerate(patents[:limit], 1):
            title = p.get("title", "Untitled")
            inventors = p.get("inventor", [])
            inv_str = ", ".join(inventors[:3]) if inventors else "?"
            year = p.get("publicationYear", "?")
            ipc = p.get("classificationIPC", [])
            ipc_str = ", ".join(ipc[:3]) if ipc else ""
            lines.append(f"## {i}. {title}\n")
            lines.append(f"- **Inventors:** {inv_str} | **Year:** {year}\n")
            if ipc_str:
                lines.append(f"- **IPC:** {ipc_str}\n")
            lines.append("")

        await ctx.info(f"Found {len(patents)} patents")
        return "\n".join(lines)

    except requests.RequestException as e:
        await ctx.warning(f"Lens.org API error (may need API key): {e}")
        return f"Lens.org API error: {e}. Note: Lens.org requires a free API key from https://lens.org."
    except Exception as e:
        await ctx.error(f"Patent search failed: {e}")
        raise DiscoveryError(str(e))


def _api_token() -> str:
    """The Lens token: environment first, then the config.

    The same order the connectors use, so a key set either way is found.
    """
    import os

    from academic_hunter.core import get_config

    token = os.environ.get("LENS_API_KEY")
    if token:
        return token

    try:
        settings = get_config().settings or {}
    except Exception:
        return ""

    keys = settings.get("api_keys") or {}
    return str(keys.get("lens") or settings.get("lens_api_key") or "")
