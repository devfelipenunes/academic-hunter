"""MCP tool for looking up researcher information via the ORCID Public API.

ORCID (https://pub.orcid.org/) provides persistent digital identifiers for
researchers. The Public API v3.0 is free and requires no API key for
read-only access to public profiles, including name, affiliations,
publications, and funding.
"""

import logging

import asyncio

import requests
from mcp.server.fastmcp import Context

from ..cache import cached, citation_cache
from ..exceptions import DiscoveryError
from ..validation import validate_orcid

logger = logging.getLogger("academic_hunter.mcp.orcid")
ORCID_API = "https://pub.orcid.org/v3.0"


@cached(citation_cache)
async def lookup_orcid(ctx: Context, orcid_id: str) -> str:
    """Looks up a researcher's profile and publications via ORCID.

    Args:
        ctx: FastMCP Context (auto-injected).
        orcid_id: ORCID identifier (e.g., "0000-0002-1825-0097").

    Returns:
        A Markdown-formatted summary of the researcher's profile including
        name, affiliations, and recent publications.
    """
    await ctx.info(f"Looking up ORCID {orcid_id}...")
    try:
        orcid_id = validate_orcid(orcid_id)
        headers = {"Accept": "application/json"}
        url = f"{ORCID_API}/{orcid_id}/record"
        resp = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        person = data.get("person") or {}
        name_data = person.get("name") or {}
        given = _value(name_data.get("given-names"))
        family = _value(name_data.get("family-name"))
        credit = _value(name_data.get("credit-name"), f"{given} {family}")

        lines = [f"# ORCID Profile: {credit}\n", f"**ORCID:** https://orcid.org/{orcid_id}\n"]

        # Affiliations
        employments = _employments(data)
        if employments:
            lines.append("\n## Affiliations\n")
            for emp in employments[:5]:
                org = (emp.get("organization") or {}).get("name") or "?"
                dept = emp.get("department-name", "") or ""
                role = emp.get("role-title", "") or ""
                parts = []
                if dept:
                    parts.append(dept)
                if role:
                    parts.append(role)
                suffix = f" ({', '.join(parts)})" if parts else ""
                lines.append(f"- {org}{suffix}\n")

        # Publications
        activities = data.get("activities-summary") or {}
        works = (activities.get("works") or {}).get("group", [])
        if works:
            lines.append("\n## Recent Publications\n")
            for work in works[:10]:
                summary = work.get("work-summary", [{}])[0]
                title = summary.get("title", {}).get("title", {}).get("value", "Untitled")
                pub_date = summary.get("publication-date", {})
                year_val = pub_date.get("year", {}) or {}
                year = year_val.get("value", "?")
                doi = ""
                for ext_id in summary.get("external-ids", {}).get("external-id", []):
                    if ext_id.get("external-id-type") == "doi":
                        doi = ext_id.get("external-id-value", "")
                lines.append(f"- **{title}** ({year})")
                if doi:
                    lines.append(f"  DOI: `{doi}`")
                lines.append("")

        await ctx.info(f"ORCID lookup complete for {credit}")
        return "\n".join(lines)

    except ValueError as e:
        raise DiscoveryError(str(e))
    except requests.RequestException as e:
        await ctx.error(f"ORCID API error: {e}")
        raise DiscoveryError(str(e))
    except Exception as e:
        await ctx.error(f"ORCID lookup failed: {e}")
        raise DiscoveryError(str(e))


def _value(node, default: str = "?") -> str:
    """ORCID wraps every scalar as ``{"value": ...}``.

    A field the researcher left out arrives as an explicit ``null`` rather than
    absent, so `.get(name, {})` returns `None` and the next `.get` was a call on
    it — which failed the whole lookup.
    """
    if not isinstance(node, dict):
        return default
    value = node.get("value")
    return str(value) if value else default


def _employments(record: dict) -> list:
    """The employment summaries of a record, flattened.

    They live under ``activities-summary``, nested through ``affiliation-group``
    and ``summaries``. Read from ``person`` — where they never are — the
    affiliations section was always empty while the record carried the data.
    """
    activities = (record.get("activities-summary") or {}).get("employments") or {}
    summaries = []
    for group in activities.get("affiliation-group") or []:
        for entry in group.get("summaries") or []:
            summary = entry.get("employment-summary")
            if summary:
                summaries.append(summary)
    return summaries
