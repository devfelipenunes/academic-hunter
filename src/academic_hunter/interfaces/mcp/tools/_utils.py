"""Shared utilities and constants for MCP tools."""

import logging
import os
from pathlib import Path
from academic_hunter import AcademicHunter
from academic_hunter.plugins.vector_stores import ChromaVectorStore
import academic_hunter as pkg

logger = logging.getLogger("academic_hunter.mcp._utils")

_STOPWORDS = {
    "the", "a", "an", "of", "in", "for", "and", "or", "to", "with",
    "on", "at", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "but",
    "not", "what", "which", "who", "whom", "this", "that", "these",
    "those", "it", "its", "study", "research", "paper", "approach",
    "method", "result", "analysis", "based", "using", "new", "novel",
}


def get_project_root() -> Path:
    """Resolve the project root from the package location."""
    pkg_init = Path(pkg.__file__).resolve()
    for parent in [pkg_init] + list(pkg_init.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def _get_vector_store():
    """Initialize and return a ChromaVectorStore instance.

    The database path is derived from the project root directly. It used to be
    read off ``AcademicHunter(...).output_dir.parent``, which built a whole
    hunter — config parse, SQLite cache, eight connectors, semantic screener —
    on every tool call just to compute a path. With the hunter mocked in tests
    the path string became a MagicMock repr, and ChromaDB duly created a
    directory named after it in the repository.
    """
    try:
        db_dir = str(get_project_root() / ".academic_hunter" / "chroma_db")
        return ChromaVectorStore(db_dir=db_dir)
    except Exception as e:
        logger.warning("Could not initialize vector store: %s", e)
        return None


def _make_hunter() -> AcademicHunter:
    """Create an AcademicHunter rooted at the project directory."""
    return AcademicHunter(output_dir=str(get_project_root() / "results"))


def _load_latest_papers() -> list:
    """Papers from the most recent run, read back from disk.

    Every MCP tool call builds its own ``AcademicHunter``, whose
    ``consolidated_results`` is always empty — the run that produced the papers
    lives in the hunter owned by that ``run_search`` call, and nothing carries it
    across. So a tool that wants "the papers" has to read them back, and this is
    that read: the newest ``academic_dataset_*.csv`` under ``results/``.

    Recursive on purpose — ``CsvExporter`` writes inside a per-run directory
    (``run_<ts>/``), so a non-recursive glob finds nothing. That mismatch is why
    ``export_report`` and ``index_papers`` both used to answer "no results" right
    after a successful search.
    """
    results_dir = get_project_root() / "results"
    csv_files = sorted(
        results_dir.rglob("academic_dataset_*.csv"),
        key=os.path.getctime,
        reverse=True,
    )
    if not csv_files:
        return []
    try:
        import pandas as pd

        frame = pd.read_csv(csv_files[0])
        # pandas turns an empty cell into NaN, and NaN is a *float*: it is
        # truthy-checked as present, stringifies to "nan", and makes Chroma
        # reject the batch ("Expected ID to be a str, got nan"). Callers expect
        # the missing value, so hand them None.
        cleaned = frame.astype(object).where(frame.notna(), None)
        return cleaned.to_dict(orient="records")
    except Exception as e:
        logger.warning("Could not read %s: %s", csv_files[0], e)
        return []
