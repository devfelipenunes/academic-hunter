"""MCP tool for exporting search results in CSV, JSON, BibTeX, or RIS format.

Accepts a ``ctx: Context`` parameter (auto-injected by FastMCP)
for logging and progress reporting.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from academic_hunter import AcademicHunter
from academic_hunter.core.infra import paths
from academic_hunter.core.models.authors import split_authors
from academic_hunter.core.models.utils import (
    bibtex_authors,
    escape_bibtex,
    neutralise_formula,
    one_line,
)
from academic_hunter.core.writing.style import paper_citation_key
from mcp.server.fastmcp import Context

from ..exceptions import SearchError
from ._utils import _load_latest_papers, get_project_root, run_blocking

logger = logging.getLogger("academic_hunter.mcp.export")


def _free_path(directory, stem: str, ext: str):
    """A path under ``directory`` that nothing has written yet.

    The default name carried a second-resolution timestamp and nothing else, so
    two exports of the same format inside one second resolved to the same file
    and the second silently replaced the first — with both calls reporting
    success and naming the same path.
    """
    candidate = directory / f"{stem}.{ext}"
    counter = 2
    while candidate.exists():
        candidate = directory / f"{stem}_{counter}.{ext}"
        counter += 1
    return candidate


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
        hunter = await run_blocking(
            AcademicHunter, output_dir=str(project_root / paths.RESULTS_DIRNAME)
        )
        papers = list(hunter.consolidated_results.values())

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
        results_dir = project_root / paths.RESULTS_DIRNAME
        results_dir.mkdir(parents=True, exist_ok=True)

        if output_path is None:
            output_path = str(_free_path(results_dir, f"export_{timestamp}", ext))

        if format_lower == "csv":
            import pandas as pd

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

    The key comes from ``paper_citation_key``, the same function
    ``paper_context`` names keys with — the agent is told to cite a key
    verbatim, so the two writers must not derive it differently.
    """
    lines = []
    for paper in papers:
        doi = paper.get("DOI", "")
        title = paper.get("Title", "")
        year = paper.get("Year", "")
        key = paper_citation_key(paper)

        authors = bibtex_authors(paper.get("Authors", paper.get("author", "")))

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

        for author in split_authors(paper.get("Authors", paper.get("author", ""))):
            entry.append(f"AU  - {one_line(author)}")

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
