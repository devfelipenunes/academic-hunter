"""MCP tool for exporting search results in CSV, JSON, BibTeX, or RIS format.

Accepts a ``ctx: Context`` parameter (auto-injected by FastMCP)
for logging and progress reporting.
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional

from mcp.server.fastmcp import Context

from academic_hunter import AcademicHunter
from ._utils import _load_latest_papers, get_project_root
from ..exceptions import SearchError

logger = logging.getLogger("academic_hunter.mcp.export")


async def export_report(
    ctx: Context, format: str = "csv", output_path: Optional[str] = None
) -> str:
    """Exports the latest consolidated search results in CSV, JSON, BibTeX, or RIS format.

    Args:
        ctx: FastMCP Context (auto-injected).
        format: Export format — ``"csv"`` (default), ``"json"``, ``"bibtex"``, or ``"ris"``.
        output_path: Full path for the output file.  If omitted, the file is
                     written to ``results/export_{timestamp}.{ext}``.
    """
    await ctx.info(f"Exporting report in {format} format")

    try:
        project_root = get_project_root()
        hunter = AcademicHunter(output_dir=str(project_root / "results"))
        papers = list(hunter.consolidated_results.values())

        # Fallback: load from the latest run's CSV when nothing is in memory.
        # A tool call always builds its own hunter, so this is the normal path,
        # not an edge case — see `_load_latest_papers`.
        if not papers:
            await ctx.info("No in-memory results, trying latest CSV...")
            papers = _load_latest_papers()
            if papers:
                await ctx.info(f"Loaded {len(papers)} papers from the latest run")

        if not papers:
            await ctx.info("No search results to export")
            return "No search results to export."

        format_lower = format.lower()
        supported_formats = ("csv", "json", "bibtex", "ris")
        if format_lower not in supported_formats:
            await ctx.error(f"Unsupported format: {format}")
            return "Unsupported format. Use 'csv', 'json', 'bibtex', or 'ris'."

        ext_map = {"csv": "csv", "json": "json", "bibtex": "bib", "ris": "ris"}
        ext = ext_map[format_lower]

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_dir = project_root / "results"
        results_dir.mkdir(parents=True, exist_ok=True)

        if output_path is None:
            output_path = str(results_dir / f"export_{timestamp}.{ext}")

        if format_lower == "csv":
            import pandas as pd  # lazy import

            df = pd.DataFrame(papers)
            df.to_csv(output_path, index=False)

        elif format_lower == "json":
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(papers, f, indent=2, ensure_ascii=False, default=str)

        elif format_lower == "bibtex":
            _write_bibtex(papers, output_path)

        elif format_lower == "ris":
            _write_ris(papers, output_path)

        await ctx.info(f"Exported {len(papers)} papers to {output_path}")
        return f"Successfully exported {len(papers)} papers to {output_path}"

    except SearchError:
        raise
    except Exception as e:
        await ctx.error(f"Failed to export report: {e}")
        raise SearchError(str(e))


def _write_bibtex(papers: list, output_path: str) -> None:
    """Write papers to a BibTeX file.

    Each paper produces an ``@article{...}`` entry with author, title,
    journal, year, url, doi, and abstract fields where available.
    """
    lines = []
    for i, paper in enumerate(papers):
        doi = paper.get("DOI", "")
        key = doi.replace("/", "-").replace("_", "-") if doi else f"paper_{i + 1}"

        authors = paper.get("Authors", paper.get("author", ""))
        if isinstance(authors, list):
            authors = " and ".join(authors)

        title = paper.get("Title", "")
        journal = paper.get("Source", "")
        year = paper.get("Year", "")
        url = paper.get("URL", "")
        abstract = paper.get("Abstract", "")

        lines.append(f"@article{{{key},")
        if authors:
            lines.append(f"  author = {{{authors}}},")
        if title:
            lines.append(f"  title = {{{title}}},")
        if journal:
            lines.append(f"  journal = {{{journal}}},")
        if year:
            lines.append(f"  year = {{{year}}},")
        if url:
            lines.append(f"  url = {{{url}}},")
        if doi:
            lines.append(f"  doi = {{{doi}}},")
        if abstract:
            lines.append(f"  abstract = {{{abstract}}},")
        lines.append("}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _write_ris(papers: list, output_path: str) -> None:
    """Write papers to a RIS file.

    Each paper produces a RIS record with fields for type (JOUR),
    title (TI), authors (AU), year (PY), journal (JO), DOI (DO),
    abstract (AB), and URL (UR).
    """
    records = []
    for paper in papers:
        entry = ["TY  - JOUR"]

        title = paper.get("Title", "")
        if title:
            entry.append(f"TI  - {title}")

        authors = paper.get("Authors", paper.get("author", ""))
        if isinstance(authors, list):
            for a in authors:
                entry.append(f"AU  - {a}")
        elif authors:
            entry.append(f"AU  - {authors}")

        year = paper.get("Year", "")
        if year:
            entry.append(f"PY  - {year}")

        journal = paper.get("Source", "")
        if journal:
            entry.append(f"JO  - {journal}")

        doi = paper.get("DOI", "")
        if doi:
            entry.append(f"DO  - {doi}")

        abstract = paper.get("Abstract", "")
        if abstract:
            entry.append(f"AB  - {abstract}")

        url = paper.get("URL", "")
        if url:
            entry.append(f"UR  - {url}")

        entry.append("ER  - ")
        records.append("\n".join(entry))

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(records) + "\n")
