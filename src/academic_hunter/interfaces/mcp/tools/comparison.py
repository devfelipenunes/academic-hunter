"""MCP tool for side-by-side paper comparison using Semantic Scholar metadata.

Accepts a ``ctx: Context`` parameter (auto-injected by FastMCP)
for logging and progress reporting.
"""

import logging
import re

import asyncio
import requests
from mcp.server.fastmcp import Context

from academic_hunter import AcademicHunter
from ._utils import _STOPWORDS
from ..exceptions import DiscoveryError

logger = logging.getLogger("academic_hunter.mcp.comparison")


async def compare_papers(ctx: Context, doi_a: str, doi_b: str) -> str:
    """Compares two papers side by side using Semantic Scholar metadata.

    Fetches title, year, and abstract for both DOIs, computes shared keywords
    from their abstracts, and presents a formatted comparison.

    Args:
        ctx: FastMCP Context (auto-injected).
        doi_a: DOI of the first paper.
        doi_b: DOI of the second paper.
    """
    await ctx.info(f"Comparing papers: {doi_a} vs {doi_b}")

    try:
        async def _fetch_meta(doi: str) -> dict:
            """Fetch paper metadata — tries Semantic Scholar, falls back to AcademicHunter."""
            last_error = None
            # Try Semantic Scholar API
            try:
                url = (
                    f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
                    "?fields=title,year,abstract"
                )
                resp = await asyncio.to_thread(requests.get, url, timeout=10)
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as e:
                last_error = e

            # Fallback: arXiv DOIs (10.48550/arXiv.xxxx) not found by Semantic Scholar
            try:
                hunter = AcademicHunter()
                abstract = hunter.fetch_abstract_by_doi(doi)
                if abstract:
                    title = abstract.strip().split("\n")[0][:80] if abstract else doi
                    return {"title": title, "year": None, "abstract": abstract}
            except Exception as e:
                last_error = e

            # Both attempts failed — re-raise the original error
            raise DiscoveryError(str(last_error)) if last_error else DiscoveryError(f"Paper {doi} not found")

        def _keyword_set(text: str) -> set[str]:
            """Extract meaningful keywords from text."""
            words = re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", text.lower())
            return {w for w in words if w not in _STOPWORDS}

        # Fetch metadata for both papers
        meta_a = await _fetch_meta(doi_a)
        meta_b = await _fetch_meta(doi_b)

        hunter = AcademicHunter()

        title_a = meta_a.get("title") or "Unknown Title"
        title_b = meta_b.get("title") or "Unknown Title"
        year_a = meta_a.get("year") or "Unknown Year"
        year_b = meta_b.get("year") or "Unknown Year"

        abstract_a = meta_a.get("abstract") or ""
        if not abstract_a:
            abstract_a = hunter.fetch_abstract_by_doi(doi_a) or ""

        abstract_b = meta_b.get("abstract") or ""
        if not abstract_b:
            abstract_b = hunter.fetch_abstract_by_doi(doi_b) or ""

        # Compute shared keywords
        kw_a = _keyword_set(abstract_a)
        kw_b = _keyword_set(abstract_b)
        shared = sorted(kw_a & kw_b)

        # Format abstract previews (first 400 chars)
        preview_a = (abstract_a[:400] + "...") if len(abstract_a) > 400 else (abstract_a or "*Not found*")
        preview_b = (abstract_b[:400] + "...") if len(abstract_b) > 400 else (abstract_b or "*Not found*")

        lines = [
            "# Paper Comparison\n",
            "| Field | Paper A | Paper B |",
            "|-------|---------|---------|",
            f"| **DOI** | `{doi_a}` | `{doi_b}` |",
            f"| **Title** | {title_a} | {title_b} |",
            f"| **Year** | {year_a} | {year_b} |",
            "",
            "## Abstract Preview — Paper A",
            preview_a,
            "",
            "## Abstract Preview — Paper B",
            preview_b,
            "",
        ]

        if shared:
            lines.append(f"## Shared Keywords ({len(shared)})")
            lines.append(", ".join(shared))
        else:
            lines.append("## Shared Keywords")
            lines.append("*No significant keyword overlap found.*")

        lines.append("")
        await ctx.info("Comparison complete")
        return "\n".join(lines)

    except DiscoveryError:
        await ctx.error("Failed to compare papers")
        raise
    except Exception as e:
        await ctx.error(f"Failed to compare papers: {e}")
        raise DiscoveryError(str(e))
