"""Shared utilities and constants for MCP tools."""

import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Callable
from academic_hunter import AcademicHunter
from academic_hunter.core.ports.vector_store import PaperListingPort
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


async def run_blocking(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run synchronous work off the event loop.

    Every tool on this server shares one event loop. A tool that calls blocking
    code — a pipeline that joins threads for minutes, an ONNX encode, a pandas
    read — freezes every other request for as long as it takes, including the
    SSE heartbeat that keeps the connection alive. The HTTP tools here already
    offload their requests; this is the same treatment for the heavy local work,
    in one place so the reasoning travels with it.
    """
    return await asyncio.to_thread(fn, *args, **kwargs)


def get_project_root() -> Path:
    """Resolve the project root from the package location."""
    pkg_init = Path(pkg.__file__).resolve()
    for parent in [pkg_init] + list(pkg_init.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def _get_vector_store():
    """Initialize and return a ChromaVectorStore instance.

    The path comes from the project root, not from an ``AcademicHunter``: that
    built a whole hunter per call just to compute a path.
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


def _newest_run_artifact(paths):
    """The path whose filename carries the latest run stamp, or None.

    Not `getctime`: on Linux that is metadata-change time, and a file with no run
    stamp at all (a test's leftovers) sorted as the newest run.
    """
    newest, newest_stamp = None, ""
    for path in paths:
        match = re.search(r"(\d{8}_\d{6})", path.name)
        if not match:
            continue
        if match.group(1) > newest_stamp:
            newest, newest_stamp = path, match.group(1)
    return newest


def _latest_run_dir() -> Path | None:
    """Directory of the most recent run, whichever artifact it left behind.

    A run writes its dataset and its ``run_stats`` into the same directory, so
    asking once answers for both; looking them up independently would mix two
    runs whenever one of them is missing.
    """
    results_dir = get_project_root() / "results"
    candidates = [
        path
        for pattern in ("academic_dataset_*.csv", "run_stats_*.json")
        for path in results_dir.rglob(pattern)
    ]
    newest = _newest_run_artifact(candidates)
    return newest.parent if newest else None


def _latest_report_path(results_dir: Path) -> Path | None:
    """The report of the most recent run, or None.

    `RELATORIO_ELITE_*` rather than any `.md`: the manager writes `export_results`
    and then `generate_prisma_report`, so the PRISMA flow lands in the same
    directory *after* the report. Selecting by `mtime` over every Markdown handed
    a client asking for the latest report a Mermaid diagram of the screening
    counters.

    Chosen by the run stamp in the name, like the other readers here — `ctime` is
    metadata-change time on Linux, so copying a file made it "the latest".
    """
    candidates = list(results_dir.rglob("RELATORIO_ELITE_*.md"))
    if not candidates:
        candidates = list(results_dir.glob("*.md"))
    if not candidates:
        return None

    stamped = _newest_run_artifact(candidates)
    if stamped is not None:
        return stamped
    # A report with no run stamp in its name; nothing to order it by but time.
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _load_latest_papers() -> list:
    """Papers from the most recent run, read back from disk.

    A tool call always builds its own ``AcademicHunter``, whose results are
    empty, so this is the normal way to reach "the papers", not a fallback.
    Recursive because the exporter writes into a per-run subdirectory.
    """
    results_dir = get_project_root() / "results"
    csv_path = _newest_run_artifact(results_dir.rglob("academic_dataset_*.csv"))
    if csv_path is None:
        return []
    try:
        import pandas as pd

        frame = pd.read_csv(csv_path)
        # pandas makes an empty cell NaN — a float that stringifies to "nan" and
        # makes Chroma reject the batch. Callers expect the missing value.
        cleaned = frame.astype(object).where(frame.notna(), None)
        return cleaned.to_dict(orient="records")
    except Exception as e:
        logger.warning("Could not read %s: %s", csv_path, e)
        return []


def corpus_of(store, fallback_top_k: int = 1000) -> list:
    """The papers an analysis of the corpus should describe.

    Reading the collection is what makes clustering, trends and duplicate
    detection statements about the corpus. A similarity query answers a different
    question — which documents sit nearest a phrase — and the analyses then
    describe that neighbourhood instead, without saying so.

    `fallback_top_k` is reached only for a store that cannot list, where a query
    is all there is; the warning names the consequence rather than hiding it.
    """
    if isinstance(store, PaperListingPort):
        return store.all_papers()

    logger.warning(
        "The vector store cannot list its collection; falling back to a "
        "similarity query, so this analysis describes a sample of it."
    )
    return store.query("research paper", top_k=fallback_top_k)
