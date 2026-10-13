"""MCP tool for finding open-access versions of papers via Unpaywall.

Unpaywall (https://api.unpaywall.org/v2/) indexes open-access versions of
paywalled papers using DOIs.  An email address is not optional: Unpaywall
answers 422 without a contact address it accepts, and it refuses the placeholder
domains this kind of documentation usually ships. So the address is taken from
the configuration when the caller does not pass one.

The HTTP call lives in ``plugins/fulltext/unpaywall.py`` so the pipeline can use
it without importing this layer; this tool keeps the presentation concerns.
"""

import asyncio
import logging

from academic_hunter.core.ports.fulltext import (
    FullTextConfigError,
    FullTextTransientError,
    NoOpenAccessVersion,
)
from academic_hunter.plugins.fulltext.unpaywall import fetch_record
from mcp.server.fastmcp import Context

from ..exceptions import DiscoveryError
from ..validation import validate_doi, validate_email

logger = logging.getLogger("academic_hunter.mcp.unpaywall")


async def find_open_access(ctx: Context, doi: str, email: str = "") -> str:
    """Finds the open-access version of a paper by DOI via Unpaywall.

    Returns OA status, best location URL, and license info.

    With no ``email`` passed, the address configured under
    ``settings.fulltext.email`` is used, falling back to ``settings.user_email``
    -- the same resolution the full-text step performs, so one setting serves
    both and neither can drift from the other.

    Args:
        ctx: FastMCP Context (auto-injected).
        doi: DOI of the paper.
        email: Contact address for Unpaywall. Defaults to the configured one.
    """
    await ctx.info(f"Looking up OA version for DOI {doi}...")
    try:
        doi = validate_doi(doi)
        if not email:
            from academic_hunter.core import get_config

            email = str(get_config().fulltext_config().get("email") or "")
        if email:
            email = validate_email(email)

        data = await asyncio.to_thread(fetch_record, doi, email)

        is_oa = data.get("is_oa", False)
        oa_status = data.get("oa_status", "closed")
        best_loc = data.get("best_oa_location", {})

        lines = [
            f"# Open Access Status: {doi}\n",
            f"**OA:** {'✅ Yes' if is_oa else '❌ No'}\n",
            f"**Status:** {oa_status}\n",
        ]

        if best_loc:
            url = best_loc.get("url_for_pdf") or best_loc.get("url") or ""
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

    except FullTextConfigError:
        await ctx.warning("Unpaywall requires a valid email")
        return (
            "Unpaywall needs a contact address it accepts, and none is "
            "configured. Pass `email`, or set `settings.fulltext.email` (or "
            "`settings.user_email`) in config.json. Placeholder domains such as "
            "example.com are refused."
        )
    except NoOpenAccessVersion:
        await ctx.info(f"Unpaywall has no record for {doi}")
        return f"# Open Access Status: {doi}\n\n**OA:** ❌ No\n**Status:** not found\n"
    except FullTextTransientError as e:
        await ctx.error(f"Unpaywall API error: {e}")
        raise DiscoveryError(str(e))
    except ValueError as e:
        raise DiscoveryError(str(e))
    except Exception as e:
        await ctx.error(f"Failed to find OA version: {e}")
        raise DiscoveryError(str(e))
