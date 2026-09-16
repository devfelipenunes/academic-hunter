"""MCP tool for side-by-side paper comparison using OpenAlex metadata.

Accepts a ``ctx: Context`` parameter (auto-injected by FastMCP)
for logging and progress reporting.
"""

import logging
import re

import requests
from urllib.parse import quote
from mcp.server.fastmcp import Context

from academic_hunter import AcademicHunter
from academic_hunter.plugins.connectors.openalex import decode_abstract
from ._utils import _STOPWORDS, openalex_get, run_blocking
from ..exceptions import DiscoveryError
from ..validation import validate_doi

logger = logging.getLogger("academic_hunter.mcp.comparison")


async def compare_papers(ctx: Context, doi_a: str, doi_b: str) -> str:
    """Compares two papers side by side using OpenAlex metadata.

    Fetches title, year, and abstract for both DOIs, computes shared keywords
    from their abstracts, and presents a formatted comparison. Both lookups are
    DOI singletons, which OpenAlex does not charge for.

    Args:
        ctx: FastMCP Context (auto-injected).
        doi_a: DOI of the first paper.
        doi_b: DOI of the second paper.
    """
    await ctx.info(f"Comparing papers: {doi_a} vs {doi_b}")

    try:
        doi_a = validate_doi(doi_a)
        doi_b = validate_doi(doi_b)

        async def _fetch_meta(doi: str) -> dict:
            """Fetch paper metadata — tries OpenAlex, falls back to AcademicHunter."""
            last_error = None
            # A DOI lookup is OpenAlex's free call type: it costs no credits,
            # where the `search` endpoint costs ten.
            try:
                # `or {}`: a 200 with nothing in it is a degenerate answer, not
                # a failure — the comparison degrades to "Unknown Title" rather
                # than aborting. An HTTP error is the failure, and that falls
                # through to the hunter below.
                work = await openalex_get(
                    f"/works/doi:{quote(doi, safe='/')}",
                    {"select": "display_name,publication_year,abstract_inverted_index"},
                ) or {}
                return {
                    "title": work.get("display_name"),
                    "year": work.get("publication_year"),
                    "abstract": decode_abstract(work.get("abstract_inverted_index")),
                }
            except requests.RequestException as e:
                last_error = e

            # Fallback: DOIs OpenAlex does not hold, arXiv's included.
            try:
                hunter = await run_blocking(AcademicHunter)
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

        async def _abstract_for(meta: dict, doi: str) -> str:
            abstract = meta.get("abstract") or ""
            if abstract:
                return abstract
            hunter = await run_blocking(AcademicHunter)
            return hunter.fetch_abstract_by_doi(doi) or ""

        title_a = meta_a.get("title") or "Unknown Title"
        title_b = meta_b.get("title") or "Unknown Title"
        year_a = meta_a.get("year") or "Unknown Year"
        year_b = meta_b.get("year") or "Unknown Year"

        abstract_a = await _abstract_for(meta_a, doi_a)
        abstract_b = await _abstract_for(meta_b, doi_b)

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

    except ValueError as e:
        raise DiscoveryError(str(e))
    except DiscoveryError:
        await ctx.error("Failed to compare papers")
        raise
    except Exception as e:
        await ctx.error(f"Failed to compare papers: {e}")
        raise DiscoveryError(str(e))
