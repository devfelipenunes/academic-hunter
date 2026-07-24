"""MCP tools for paper analysis — trending topics, paper comparison, and report export.

All tools accept a ``ctx: Context`` parameter (auto-injected by FastMCP)
for logging and progress reporting.
"""

import json
import logging
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import Context

from academic_hunter import AcademicHunter
from academic_hunter.plugins.vector_stores import ChromaVectorStore
from ._utils import get_project_root
from ..exceptions import DiscoveryError, SearchError

logger = logging.getLogger("academic_hunter.mcp.analysis")

_STOPWORDS = {
    "the", "a", "an", "of", "in", "for", "and", "or", "to", "with",
    "on", "at", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "but",
    "not", "what", "which", "who", "whom", "this", "that", "these",
    "those", "it", "its", "study", "research", "paper", "approach",
    "method", "result", "analysis", "based", "using", "new", "novel",
}


def _get_vector_store():
    """Initialize the ChromaDB vector store (same pattern as rag.py)."""
    try:
        hunter = AcademicHunter(output_dir=str(get_project_root() / "results"))
        db_dir = str(hunter.output_dir.parent / ".academic_hunter" / "chroma_db")
        return ChromaVectorStore(db_dir=db_dir)
    except Exception:
        return None


def _extract_bigrams(title: str, stopwords: set) -> list[str]:
    """Extract meaningful bigrams from a title, excluding stopwords."""
    import re

    words = re.findall(r"[a-zA-Z][a-zA-Z\-]{1,}", title.lower())
    filtered = [w for w in words if w not in stopwords and len(w) > 2]
    bigrams = []
    for i in range(len(filtered) - 1):
        bigrams.append(f"{filtered[i]} {filtered[i+1]}")
    return bigrams


async def trending_topics(ctx: Context, days: int = 30, min_papers: int = 3) -> str:
    """Analyzes indexed papers to identify trending research topics.

    Extracts keyword bigrams from paper titles, groups related papers,
    and returns the top clusters by frequency.

    Args:
        ctx: FastMCP Context (auto-injected).
        days: Lookback window for papers to consider (default 30, currently unused
              since vector store does not filter by date).
        min_papers: Minimum papers sharing a bigram to be considered a trend
                    (default 3).
    """
    await ctx.info("Analyzing trending topics from indexed papers...")
    store = _get_vector_store()
    if store is None:
        await ctx.error("Vector store not available")
        return "Vector store not available. Index papers first."

    # Retrieve all indexed papers via a broad query with a high limit.
    # ChromaDB will clamp n_results to the collection size.
    results = store.query("research paper topic analysis", top_k=1000)

    if not results:
        await ctx.info("No indexed papers found")
        return "No trending topics found. Index papers first."

    bigram_counter: Counter = Counter()
    bigram_titles: dict[str, list[str]] = {}

    for paper in results:
        title = paper.get("title", "")
        if not title:
            continue
        bigrams = _extract_bigrams(title, _STOPWORDS)
        for bg in bigrams:
            bigram_counter[bg] += 1
            if bg not in bigram_titles:
                bigram_titles[bg] = []
            if title not in bigram_titles[bg]:
                bigram_titles[bg].append(title)

    # Filter by minimum paper count and take top 10
    candidates = [
        (bg, count, bigram_titles[bg])
        for bg, count in bigram_counter.most_common()
        if count >= min_papers
    ]
    top_topics = candidates[:10]

    if not top_topics:
        await ctx.info("No trending topics met the minimum threshold")
        return "No trending topics found. Index papers first."

    lines = [
        "# Trending Research Topics\n",
        f"**Total papers analyzed:** {len(results)}\n",
        f"**Minimum papers per topic:** {min_papers}\n",
        "---\n",
    ]

    for i, (bigram, count, titles) in enumerate(top_topics, 1):
        lines.append(f"## {i}. \"{bigram.title()}\" ({count} papers)\n")
        for t in titles[:5]:
            lines.append(f"- {t}")
        if len(titles) > 5:
            lines.append(f"  *... and {len(titles) - 5} more papers*")
        lines.append("")

    await ctx.info(f"Found {len(top_topics)} trending topics from {len(results)} papers")
    return "\n".join(lines)


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
        import requests as _requests

        def _fetch_meta(doi: str) -> dict:
            """Fetch paper metadata from Semantic Scholar."""
            url = (
                f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
                "?fields=title,year,abstract"
            )
            resp = _requests.get(url, timeout=10)
            resp.raise_for_status()
            return resp.json()

        def _keyword_set(text: str) -> set[str]:
            """Extract meaningful keywords from text."""
            import re

            words = re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", text.lower())
            return {w for w in words if w not in _STOPWORDS}

        # Fetch metadata for both papers
        meta_a = _fetch_meta(doi_a)
        meta_b = _fetch_meta(doi_b)

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
        raise
    except Exception as e:
        await ctx.error(f"Failed to compare papers: {e}")
        raise DiscoveryError(str(e))


async def export_report(
    ctx: Context, format: str = "csv", output_path: Optional[str] = None
) -> str:
    """Exports the latest consolidated search results in CSV or JSON format.

    Args:
        ctx: FastMCP Context (auto-injected).
        format: Export format — ``"csv"`` (default) or ``"json"``.
        output_path: Full path for the output file.  If omitted, the file is
                     written to ``results/export_{timestamp}.{ext}``.
    """
    await ctx.info(f"Exporting report in {format} format")

    try:
        project_root = get_project_root()
        hunter = AcademicHunter(output_dir=str(project_root / "results"))
        papers = list(hunter.consolidated_results.values())

        if not papers:
            await ctx.info("No search results to export")
            return "No search results to export."

        format_lower = format.lower()
        if format_lower not in ("csv", "json"):
            await ctx.error(f"Unsupported format: {format}")
            return "Unsupported format. Use 'csv' or 'json'."

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_dir = project_root / "results"
        results_dir.mkdir(parents=True, exist_ok=True)

        if output_path is None:
            output_path = str(results_dir / f"export_{timestamp}.{format_lower}")

        if format_lower == "csv":
            import pandas as pd  # lazy import

            df = pd.DataFrame(papers)
            df.to_csv(output_path, index=False)
        else:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(papers, f, indent=2, ensure_ascii=False, default=str)

        await ctx.info(f"Exported {len(papers)} papers to {output_path}")
        return f"Successfully exported {len(papers)} papers to {output_path}"

    except SearchError:
        raise
    except Exception as e:
        await ctx.error(f"Failed to export report: {e}")
        raise SearchError(str(e))
