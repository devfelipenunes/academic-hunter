"""MCP tool for exporting search results in CSV, JSON, BibTeX, or RIS format.

Accepts a ``ctx: Context`` parameter (auto-injected by FastMCP)
for logging and progress reporting.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from mcp.server.fastmcp import Context

from academic_hunter import AcademicHunter
from academic_hunter.core.writing.style import BibtexKeyAllocator
from academic_hunter.plugins.exporters.bibtex import escape_bibtex
from academic_hunter.plugins.exporters.csv import neutralise_formula
from academic_hunter.plugins.exporters.ris import one_line
from ._utils import _load_latest_papers, get_project_root, run_blocking
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
        # Building a hunter compiles every configured term into a regex and
        # opens the cache — measured near 0.3 s on a real config, which is a
        # third of a second that every other tool would spend waiting.
        hunter = await run_blocking(
            AcademicHunter, output_dir=str(project_root / "results")
        )
        papers = list(hunter.consolidated_results.values())

        # Fallback: load from the latest run's CSV when nothing is in memory.
        # A tool call always builds its own hunter, so this is the normal path,
        # not an edge case — see `_load_latest_papers`.
        if not papers:
            await ctx.info("No in-memory results, trying latest CSV...")
            papers = await run_blocking(_load_latest_papers)
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
            for column in df.columns:
                df[column] = df[column].map(neutralise_formula)
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
    allocate_key = BibtexKeyAllocator()
    lines = []
    for paper in papers:
        doi = paper.get("DOI", "")
        title = paper.get("Title", "")
        year = paper.get("Year", "")
        # The key `paper_context` hands the agent, so the citation it was told to
        # use is one this file contains.
        key = allocate_key(title, year)

        authors = paper.get("Authors", paper.get("author", ""))
        if isinstance(authors, list):
            authors = " and ".join(authors)

        # `Venue` is the publication; `Source` is the database it was found in.
        journal = paper.get("Venue", "")
        url = paper.get("URL", "")
        abstract = paper.get("Abstract", "")

        lines.append(f"@article{{{key},")
        for field, value in (
            ("author", authors),
            ("title", title),
            ("journal", journal),
            ("year", year),
            ("url", url),
            ("doi", doi),
            ("abstract", abstract),
        ):
            if value:
                lines.append(f"  {field} = {{{escape_bibtex(value)}}},")
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
            entry.append(f"TI  - {one_line(title)}")

        authors = paper.get("Authors", paper.get("author", ""))
        if isinstance(authors, list):
            for a in authors:
                entry.append(f"AU  - {one_line(a)}")
        elif authors:
            entry.append(f"AU  - {one_line(authors)}")

        year = paper.get("Year", "")
        if year:
            entry.append(f"PY  - {year}")

        journal = paper.get("Venue", "")
        if journal:
            entry.append(f"JO  - {one_line(journal)}")

        doi = paper.get("DOI", "")
        if doi:
            entry.append(f"DO  - {one_line(doi)}")

        abstract = paper.get("Abstract", "")
        if abstract:
            entry.append(f"AB  - {one_line(abstract)}")

        url = paper.get("URL", "")
        if url:
            entry.append(f"UR  - {one_line(url)}")

        entry.append("ER  - ")
        records.append("\n".join(entry))

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(records) + "\n")
