"""MCP tools for citation analysis via OpenCitations/COCI.

OpenCitations is a free, open database of 2B+ citation links.
API: https://api.opencitations.net/index/v2/
No API key required.
"""

import logging
import requests
from mcp.server.fastmcp import Context
from ..exceptions import DiscoveryError

logger = logging.getLogger("academic_hunter.mcp.citations")
COCI_API = "https://api.opencitations.net/index/v1"


def _coci_request(endpoint: str, doi: str) -> list:
    """Make a request to the OpenCitations API.  Response is always a JSON list."""
    url = f"{COCI_API}/{endpoint}/{doi}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()


async def get_citation_count(ctx: Context, doi: str) -> str:
    """Returns the number of citations a paper has received via OpenCitations.

    Args:
        ctx: FastMCP Context (auto-injected).
        doi: The DOI of the paper to look up.
    """
    await ctx.info(f"Looking up citation count for DOI {doi}...")
    try:
        data = _coci_request("citation-count", doi)
        count = int(data[0]["count"]) if data else 0
        await ctx.info(f"DOI {doi} has {count} citations")
        return f"DOI {doi} has {count} citations according to OpenCitations."
    except Exception as e:
        await ctx.error(f"Failed to get citation count: {e}")
        raise DiscoveryError(str(e))


async def get_citing_papers(ctx: Context, doi: str, limit: int = 10) -> str:
    """Lists the papers that cite a given DOI.

    Args:
        ctx: FastMCP Context (auto-injected).
        doi: The DOI of the paper.
        limit: Max citing papers to show (default 10).
    """
    await ctx.info(f"Finding citing papers for DOI {doi}...")
    try:
        citations = _coci_request("citations", doi)

        if not citations:
            await ctx.info(f"No citations found for DOI {doi}")
            return f"No citations found for DOI {doi}."

        lines = [f"# Citing Papers for {doi}\n", f"**Total citations:** {len(citations)}\n", "---\n"]
        for i, c in enumerate(citations[:limit], 1):
            citing = c.get("citing", "?")
            created = c.get("creation", "?")
            span = c.get("timespan", "?")
            lines.append(f"{i}. `{citing}` (cited after {span}, indexed {created})\n")
        if len(citations) > limit:
            lines.append(f"\n*... and {len(citations) - limit} more*")

        await ctx.info(f"Found {len(citations)} citing papers")
        return "\n".join(lines)
    except Exception as e:
        await ctx.error(f"Failed to get citing papers: {e}")
        raise DiscoveryError(str(e))
