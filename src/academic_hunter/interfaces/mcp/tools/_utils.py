"""Shared utilities and constants for MCP tools."""

import asyncio
import logging
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable
import requests
from academic_hunter import AcademicHunter
from academic_hunter.core.infra import paths
from academic_hunter.core.infra.config import HunterConfig, openalex_key
from academic_hunter.core.ports.vector_store import PaperListingPort
from academic_hunter.plugins.vector_stores import ChromaVectorStore

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
    """The directory the resolved state belongs to."""
    return paths.resolve_location().base


def _get_vector_store():
    """Initialize and return a ChromaVectorStore instance.

    The path comes from the project root, not from an ``AcademicHunter``: that
    built a whole hunter per call just to compute a path.
    """
    try:
        db_dir = str(get_project_root() / paths.DATA_DIRNAME / "chroma_db")
        return ChromaVectorStore(db_dir=db_dir)
    except Exception as e:
        logger.warning("Could not initialize vector store: %s", e)
        return None


def _make_hunter() -> AcademicHunter:
    """Create an AcademicHunter rooted at the resolved location."""
    return AcademicHunter(output_dir=str(get_project_root() / paths.RESULTS_DIRNAME))


OPENALEX_BASE = "https://api.openalex.org"

#: Seconds between OpenAlex requests from this process. The service accepts 100
#: a second; the ceiling that actually binds is the daily credit budget, so a
#: burst buys nothing and only spends the margin a 429 would need.
_OPENALEX_MIN_INTERVAL = 0.5
_openalex_pace_lock = threading.Lock()
_openalex_last_call = 0.0


def _openalex_credentials() -> tuple[dict, dict]:
    """Headers and query parameters for an OpenAlex request.

    A key is optional — the data is free and keyless use works — but it raises
    the daily budget tenfold, so it is sent whenever one is configured. The
    contact address is what puts a caller in OpenAlex's polite pool.
    """
    try:
        settings = HunterConfig().settings
    except Exception as e:
        logger.warning("Could not read the config for OpenAlex credentials: %s", e)
        return {}, {}

    key = openalex_key(settings)
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    email = settings.get("user_email") or ""
    return headers, ({"mailto": email} if email else {})


def _pace_openalex() -> None:
    """Block until the minimum interval since the last OpenAlex call has passed."""
    global _openalex_last_call
    with _openalex_pace_lock:
        wait = _OPENALEX_MIN_INTERVAL - (time.time() - _openalex_last_call)
        if wait > 0:
            time.sleep(wait)
        _openalex_last_call = time.time()


def _retry_after_seconds(response) -> float | None:
    """The wait OpenAlex asked for, when it asks for one."""
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _openalex_get_sync(path: str, params: dict | None = None, attempts: int = 3) -> dict:
    """Blocking GET against OpenAlex: paced, keyed, and at most `attempts` calls.

    The last attempt falls through to `raise_for_status` rather than looping
    again, so a spent budget surfaces as the 429 it is — callers can tell "the
    day's credits are gone" apart from "this query matched nothing".
    """
    headers, credentials = _openalex_credentials()
    merged = {**credentials, **(params or {})}

    response = None
    for attempt in range(attempts):
        _pace_openalex()
        response = requests.get(
            OPENALEX_BASE + path, params=merged, headers=headers, timeout=20
        )
        if response.status_code == 429 and attempt < attempts - 1:
            delay = _retry_after_seconds(response) or float(2 ** attempt)
            logger.warning("OpenAlex is rate limiting; waiting %.1fs", delay)
            time.sleep(min(delay, 30.0))
            continue
        break

    response.raise_for_status()
    return response.json()


async def openalex_get(path: str, params: dict | None = None) -> dict:
    """GET against OpenAlex, off the event loop.

    OpenAlex meters by cost, not by request: a singleton such as
    ``/works/doi:<doi>`` is free, a filtered list is 1 credit, and a `search` is
    10. A keyless caller gets about 1000 credits a day, so callers should reach
    for a filter or a singleton over `search` whenever the question allows.
    """
    return await run_blocking(_openalex_get_sync, path, params)


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
    results_dir = get_project_root() / paths.RESULTS_DIRNAME
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
    results_dir = get_project_root() / paths.RESULTS_DIRNAME
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
