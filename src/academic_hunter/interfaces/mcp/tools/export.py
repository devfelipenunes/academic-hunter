"""MCP tool for exporting search results in CSV, JSON, BibTeX, or RIS format.

Accepts a ``ctx: Context`` parameter (auto-injected by FastMCP)
for logging and progress reporting.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from academic_hunter import AcademicHunter
from academic_hunter.core.infra import paths
from academic_hunter.core.writing import renderers
from mcp.server.fastmcp import Context

from ..exceptions import SearchError
from ._utils import _load_latest_papers, get_project_root, run_blocking

logger = logging.getLogger("academic_hunter.mcp.export")

SUPPORTED_FORMATS = ("csv", "json", "bibtex", "ris")
EXTENSIONS = {"csv": "csv", "json": "json", "bibtex": "bib", "ris": "ris"}


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


def _renderer_for(format_lower: str):
    """The one function that renders this format, looked up at call time.

    Resolved per call rather than held in a module-level map on purpose: the same
    function renders the run's own artefacts inside the pipeline, and a lookup
    bound at import would keep serving the old object if anything ever replaced
    it.
    """
    return {
        "csv": renderers.render_csv,
        "json": renderers.render_json,
        "bibtex": renderers.render_bibtex,
        "ris": renderers.render_ris,
    }[format_lower]


async def export_report(
    ctx: Context, format: str = "csv", output_path: Optional[str] = None
) -> str:
    """Exports the latest consolidated search results in CSV, JSON, BibTeX, or RIS format.

    The file's text comes from ``core.writing.renderers``, the same functions the
    pipeline writes a run's own ``academic_dataset_*`` files with.

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
        if format_lower not in SUPPORTED_FORMATS:
            await ctx.error(f"Unsupported format: {format}")
            return "Unsupported format. Use 'csv', 'json', 'bibtex', or 'ris'."

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_dir = project_root / paths.RESULTS_DIRNAME
        results_dir.mkdir(parents=True, exist_ok=True)

        if output_path is None:
            path = _free_path(results_dir, f"export_{timestamp}", EXTENSIONS[format_lower])
        else:
            path = Path(output_path)

        path.write_text(_renderer_for(format_lower)(papers), encoding="utf-8")

        await ctx.info(f"Exported {len(papers)} papers to {path}")
        return f"Successfully exported {len(papers)} papers to {path}"

    except SearchError:
        raise
    except Exception as e:
        await ctx.error(f"Failed to export report: {e}")
        raise SearchError(str(e))
