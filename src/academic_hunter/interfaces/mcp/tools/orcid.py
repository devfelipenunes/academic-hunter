"""MCP tool for looking up researcher information via the ORCID Public API.

ORCID (https://pub.orcid.org/) provides persistent digital identifiers for
researchers. The Public API v3.0 is free and requires no API key for
read-only access to public profiles, including name, affiliations,
publications, and funding.
"""

import logging

import requests
from mcp.server.fastmcp import Context

from ..exceptions import DiscoveryError

logger = logging.getLogger("academic_hunter.mcp.orcid")
ORCID_API = "https://pub.orcid.org/v3.0"


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
        headers = {"Accept": "application/json"}
        url = f"{ORCID_API}/{orcid_id}/record"
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        person = data.get("person") or {}
        name_data = person.get("name") or {}
        given = name_data.get("given-names", {}).get("value", "?")
        family = name_data.get("family-name", {}).get("value", "?")
        credit = name_data.get("credit-name", {}).get("value", f"{given} {family}")

        lines = [f"# ORCID Profile: {credit}\n", f"**ORCID:** https://orcid.org/{orcid_id}\n"]

        # Affiliations
        employments = (person.get("employments") or {}).get("employment-summary", [])
        if employments:
            lines.append("\n## Affiliations\n")
            for emp in employments[:5]:
                org = emp.get("organization", {}).get("name", "?")
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

    except requests.RequestException as e:
        await ctx.error(f"ORCID API error: {e}")
        raise DiscoveryError(str(e))
    except Exception as e:
        await ctx.error(f"ORCID lookup failed: {e}")
        raise DiscoveryError(str(e))
