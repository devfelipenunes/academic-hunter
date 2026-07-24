"""MCP tool for finding open-access versions of papers via Unpaywall.

Unpaywall (https://api.unpaywall.org/v2/) indexes open-access versions of
paywalled papers using DOIs.  An email address is recommended for higher
rate limits but not strictly required.
"""

import logging

import requests
from mcp.server.fastmcp import Context

from ..exceptions import DiscoveryError

logger = logging.getLogger("academic_hunter.mcp.unpaywall")
UNPAYWALL_API = "https://api.unpaywall.org/v2"


async def find_open_access(ctx: Context, doi: str, email: str = "") -> str:
    """Finds the open-access version of a paper by DOI via Unpaywall.

    Returns OA status, best location URL, and license info.

    Args:
        ctx: FastMCP Context (auto-injected).
        doi: DOI of the paper.
        email: Email for Unpaywall API (optional but recommended for higher limits).
    """
    await ctx.info(f"Looking up OA version for DOI {doi}...")
    try:
        params = {"email": email} if email else {}
        url = f"{UNPAYWALL_API}/{doi}"
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        is_oa = data.get("is_oa", False)
        oa_status = data.get("oa_status", "closed")
        best_loc = data.get("best_oa_location", {})

        lines = [
            f"# Open Access Status: {doi}\n",
            f"**OA:** {'✅ Yes' if is_oa else '❌ No'}\n",
            f"**Status:** {oa_status}\n",
        ]

        if best_loc:
            url = best_loc.get("url_for_pdf", best_loc.get("url", ""))
            host = best_loc.get("host_type", "")
            license = best_loc.get("license", "")
            version = best_loc.get("version", "")
            if url:
                lines.append(f"**Best URL:** {url}\n")
            if host:
                lines.append(f"**Host:** {host}\n")
            if license:
                lines.append(f"**License:** {license}\n")
            if version:
                lines.append(f"**Version:** {version}\n")

        await ctx.info(f"OA status for {doi}: {oa_status}")
        return "\n".join(lines)

    except requests.RequestException as e:
        await ctx.error(f"Unpaywall API error: {e}")
        raise DiscoveryError(str(e))
    except Exception as e:
        await ctx.error(f"Failed to find OA version: {e}")
        raise DiscoveryError(str(e))
