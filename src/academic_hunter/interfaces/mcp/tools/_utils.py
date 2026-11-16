"""Shared utilities and constants for MCP tools."""

import asyncio
import logging
import re
import threading
from pathlib import Path
from typing import Any, Callable

import requests

from academic_hunter import AcademicHunter, __version__
from academic_hunter.core.infra import paths
from academic_hunter.core.infra.config import HunterConfig
from academic_hunter.core.infra.openalex import (
    OPENALEX_BASE,
    OPENALEX_DEFAULT_DELAY,
    OPENALEX_DOMAIN,
    openalex_headers,
    openalex_params,
)
from academic_hunter.core.infra.transport import HttpTransport
from academic_hunter.core.ports.vector_store import LEGACY_COLLECTION, PaperListingPort
from academic_hunter.plugins.vector_stores import ChromaVectorStore

logger = logging.getLogger("academic_hunter.mcp._utils")

_STOPWORDS = {
    "the", "a", "an", "of", "in", "for", "and", "or", "to", "with",
    "on", "at", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "but",
    "not", "what", "which", "who", "whom", "this", "that", "these",
    "those", "it", "its", "study", "research", "paper", "approach",
    "method", "result", "analysis", "based", "using", "new", "novel",
    "via", "toward", "towards", "within", "without", "across", "between",
    "during", "after", "before", "than", "while", "when", "where", "how",
    "why", "if", "then", "also", "such", "more", "most", "other", "both",
    "each", "every", "only", "very", "can", "could", "may", "might",
    "must", "should", "would", "will", "shall", "one", "two", "three",
}

_ACADEMIC_GENERIC_TERMS = {
    "survey", "review", "overview", "framework", "technique", "evaluation",
    "benchmark", "comparison", "comparative", "system", "application",
    "model", "learning", "training", "performance", "efficiency",
    "efficient", "accuracy", "scalability", "taxonomy", "challenge",
    "empirical", "task", "dataset", "case",
}
"""Terms that name any field's work, and are kept apart from ``_STOPWORDS``.

These two sets do different jobs and merging them would break both. A stopword
is removed from a count: the word carries nothing. A term here carries plenty --
it is a legitimate thing to score a paper on -- and what it cannot be is an
*anchor*, because the anchor gate admits a paper on any single term of the first
group that matches, so one generic anchor widens the whole gate and lets in
everything that uses the word. ``_STOPWORDS`` governs the candidate counts (and
so what can become a weight), which is why a generic term must not be added to
it: ``framework`` and ``accuracy`` are real signals on a paper, and scoring them
is fine.

Callers mark with this set, they do not filter with it. A term flagged here is
reported so the choice is visible, and the choice is the caller's.
"""


def _is_generic(term: str) -> bool:
    """Whether a term names any field's work rather than one field's.

    A phrase counts only when every word of it is generic. ``deep learning`` and
    ``language model`` carry their meaning beside a generic word, and flagging
    them would mark a topic's own vocabulary as noise.
    """
    words = str(term).split()
    return bool(words) and all(word in _ACADEMIC_GENERIC_TERMS for word in words)


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

    The collection comes from the configuration, so a tool that names none reads
    the review the config describes. Without it every call defaults to the one
    shared collection and the corpus analyses describe every review at once.
    """
    try:
        db_dir = str(get_project_root() / paths.DATA_DIRNAME / "chroma_db")
        return ChromaVectorStore(db_dir=db_dir, default_collection=_review_collection())
    except Exception as e:
        logger.warning("Could not initialize vector store: %s", e)
        return None


def _review_collection() -> str:
    """The configured review's collection, or the legacy one if unreadable."""
    try:
        return HunterConfig().collection_name()
    except Exception as e:
        logger.warning(
            "Could not read settings.collection_name (%s); using %r.",
            e, LEGACY_COLLECTION,
        )
        return LEGACY_COLLECTION


def _make_hunter() -> AcademicHunter:
    """Create an AcademicHunter rooted at the resolved location."""
    return AcademicHunter(output_dir=str(get_project_root() / paths.RESULTS_DIRNAME))


OPENALEX_BASE = OPENALEX_BASE

_OPENALEX_TRANSPORT = HttpTransport(
    lock=threading.Lock(),
    semaphore=threading.Semaphore(2),
    pacing_delays={},
    last_request_by_domain={},
    blocked_sources=set(),
    default_delay=OPENALEX_DEFAULT_DELAY,
    block_sources=False,
)


def _openalex_transport() -> HttpTransport:
    """The policy this process paces and retries OpenAlex with.

    One instance, shared by every MCP call, because pacing is about the session
    rather than the request — and it is deliberately *not* ``block_sources``:
    a review run has to finish and report the sources it could not ask, while a
    one-shot call has nothing to finish and has to say what happened. Blocking
    here would turn the second 429 of a session into a call that fails without a
    response, which is a worse message than the one the 429 itself supports.
    """
    return _OPENALEX_TRANSPORT


def _openalex_headers_and_params() -> tuple[dict, dict]:
    """What to send alongside an OpenAlex request, or empty dicts.

    Reading the config is file I/O and can fail; a caller that cannot read it
    still gets its answer, anonymously.
    """
    try:
        settings = HunterConfig().settings
    except Exception as e:
        logger.warning("Could not read the config for OpenAlex credentials: %s", e)
        return {}, {}

    return (
        openalex_headers(settings, __version__),
        openalex_params(settings),
    )


def _openalex_get_sync(path: str, params: dict | None = None, attempts: int = 3) -> dict:
    """Blocking GET against OpenAlex, over the shared transport.

    No loop and no sleeping here: how long to wait, when to retry and when to
    give up are ``core.infra.transport``'s, and the pipeline's connectors use
    the same object. What stays local is what a spent budget *means* — the
    failed attempt is handed back with its response so ``raise_for_status`` can
    raise the 429 it is, and callers can tell "the day's credits are gone" apart
    from "this query matched nothing".
    """
    headers, credentials = _openalex_headers_and_params()
    merged = {**credentials, **(params or {})}

    attempt = _openalex_transport().perform(
        lambda: requests.get(
            OPENALEX_BASE + path, params=merged, headers=headers, timeout=20
        ),
        domain=OPENALEX_DOMAIN,
        max_retries=attempts,
    )
    if attempt.ok:
        return attempt.response.json()
    if attempt.response is not None:
        attempt.response.raise_for_status()
    if attempt.error is not None:
        raise attempt.error
    raise requests.RequestException(f"OpenAlex did not answer {path}.")


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
        candidates = list(results_dir.rglob("*.md"))
    if not candidates:
        return None

    stamped = _newest_run_artifact(candidates)
    if stamped is not None:
        return stamped
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
        cleaned = frame.astype(object).where(frame.notna(), None)
        return cleaned.to_dict(orient="records")
    except Exception as e:
        logger.warning("Could not read %s: %s", csv_path, e)
        return []


def read_store_stats(store):
    """Every synchronous call the statistics views need, in one place.

    `list_collections` and `collection_stats` open the ChromaDB client and read
    the collection, both of which are blocking; a caller runs this whole batch
    through `run_blocking` rather than holding the shared event loop across
    each call in turn.
    """
    collections = store.list_collections()
    collection_data = [store.collection_stats(name) for name in collections]
    total_papers = sum(stats.get("count", 0) for stats in collection_data)
    return collections, collection_data, total_papers


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
