"""MCP tool for searching clinical trials via ClinicalTrials.gov API.

ClinicalTrials.gov (https://clinicaltrials.gov/api/v2/) provides 400K+
clinical trial records from 220+ countries.  No API key is required.
"""

import logging
import requests
from mcp.server.fastmcp import Context
from ..exceptions import DiscoveryError

logger = logging.getLogger("academic_hunter.mcp.clinicaltrials")
CT_API = "https://clinicaltrials.gov/api/v2"


async def search_clinical_trials(ctx: Context, condition: str, limit: int = 10) -> str:
    """Searches clinical trials by medical condition.

    ClinicalTrials.gov indexes 400K+ trials from 220+ countries.

    Args:
        ctx: FastMCP Context (auto-injected).
        condition: Medical condition to search (e.g., "Alzheimer's").
        limit: Max results (default 10, max 50).
    """
    await ctx.info(f"Searching clinical trials for: '{condition}'...")
    try:
        params = {
            "query.term": condition,
            "pageSize": min(limit, 50),
            "format": "json",
            "fields": "NCTId|briefTitle|overallStatus|phase|startDate|leadSponsorName|condition",
        }
        resp = requests.get(f"{CT_API}/studies", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        studies = data.get("studies", [])

        if not studies:
            await ctx.info(f"No trials found for '{condition}'")
            return f"No clinical trials found for: '{condition}'."

        lines = [
            f"# Clinical Trials: {condition}\n",
            f"**Total:** {len(studies)}\n",
            "---\n",
        ]

        for i, study in enumerate(studies[:limit], 1):
            proto = study.get("protocolSection", {}).get("identificationModule", {})
            status_mod = study.get("protocolSection", {}).get("statusModule", {})
            design = study.get("protocolSection", {}).get("designModule", {})
            sponsor = study.get("protocolSection", {}).get("sponsorCollaboratorsModule", {})

            title = proto.get("briefTitle", "Untitled")
            nct = proto.get("nctId", "?")
            status = status_mod.get("overallStatus", "?")
            phase = design.get("phases", ["N/A"])[0] if design.get("phases") else "N/A"
            sponsor_name = sponsor.get("leadSponsor", {}).get("name", "?")
            start = status_mod.get("startDateStruct", {}).get("date", "?")

            lines.append(f"## {i}. {title}\n")
            lines.append(f"- **NCT:** `{nct}` | **Status:** {status} | **Phase:** {phase}\n")
            lines.append(f"- **Sponsor:** {sponsor_name} | **Start:** {start}\n")
            lines.append("")

        await ctx.info(f"Found {len(studies)} clinical trials")
        return "\n".join(lines)

    except Exception as e:
        await ctx.error(f"ClinicalTrials.gov search failed: {e}")
        raise DiscoveryError(str(e))
