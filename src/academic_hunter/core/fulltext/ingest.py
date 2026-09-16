"""Turning DOIs into indexed chunks.

Shared by ``IngestFullTextStep`` and the ``index_fulltext`` MCP tool. It never
raises: it runs between a finished run and its report, and a publisher's 403 is
not a reason to lose the run.
"""

import logging
import time
from typing import Any, Callable, Dict, List, Mapping, Optional

from ..evaluation.qrels import doc_id_for
from ..ports.fulltext import (
    FullTextConfigError,
    FullTextTransientError,
    NoOpenAccessVersion,
)
from ..ports.vector_store import ChunkStorePort
from .chunker import chunk_document

logger = logging.getLogger("academic_hunter.fulltext")

STATUSES = (
    "obtained",
    "no_open_access",
    "download_failed",
    "no_text_layer",
    "no_sections",
    "no_doi",
    "not_attempted",
    "already_indexed",
)

DEFAULT_MAX_PAPERS = 200
DEFAULT_TIME_BUDGET = 900
DEFAULT_COLLECTION = "paper_chunks"


def ingest_full_text(
    papers: List[Dict[str, Any]],
    fetcher: Callable[[str], Any],
    store: Any,
    config: Mapping[str, Any],
    *,
    force: bool = False,
    collection_name: str = DEFAULT_COLLECTION,
) -> Dict[str, int]:
    """Fetch, chunk and index the full text of ``papers``.

    Writes ``_full_text_status`` into each paper and returns the counts. Papers
    already indexed are skipped unless ``force``; ``enabled`` is not consulted
    here, because whether to run at all is the caller's decision.
    """
    counters = {status: 0 for status in STATUSES}
    if not isinstance(store, ChunkStorePort):
        logger.info("Vector store cannot hold chunks; nothing to ingest.")
        return counters

    max_papers = int(config.get("max_papers") or DEFAULT_MAX_PAPERS)
    budget = float(config.get("time_budget_seconds") or DEFAULT_TIME_BUDGET)
    started = time.monotonic()
    attempted = 0
    failure_kinds: Dict[str, int] = {}

    for paper in papers:
        # A previous run's dataset carries this column; a stale value would be
        # attributed to an attempt that never reached a source.
        paper.pop("_full_text_source", None)

        if attempted >= max_papers or (time.monotonic() - started > budget):
            status = "not_attempted"
        else:
            doi = str(paper.get("DOI") or "").strip()
            if not doi:
                status = "no_doi"
            else:
                parent_id = doc_id_for(str(paper.get("Title", "")), doi)
                if not force and store.has_chunks(parent_id, collection_name=collection_name):
                    status = "already_indexed"
                else:
                    attempted += 1
                    try:
                        status = _ingest_one(
                            paper, doi, parent_id, fetcher, store, collection_name,
                            replace=force,
                        )
                    except FullTextConfigError as e:
                        # The chain raises this only after every source failed for
                        # *this* DOI. The sources do not share configuration, so it
                        # says nothing about the next paper — treating it as global
                        # is how one rejected e-mail silenced a whole run.
                        logger.warning("Full text needs configuration for %s: %s", doi, e)
                        status = _failed(paper, e)

        paper["_full_text_status"] = status
        counters[status] += 1
        if status == "download_failed":
            kind = paper.get("_full_text_error_kind", "unknown")
            failure_kinds[kind] = failure_kinds.get(kind, 0) + 1

    _report(counters, max_papers, budget, failure_kinds)
    return counters


def _ingest_one(
    paper: Dict[str, Any],
    doi: str,
    parent_id: str,
    fetcher: Callable[[str], Any],
    store: Any,
    collection_name: str,
    *,
    replace: bool = False,
) -> str:
    """Fetch, chunk and index one paper. Returns its status.

    Raises:
        FullTextConfigError: no source could be used for this DOI. Propagated so
            the caller records it against the paper rather than swallowing it —
            it is not a reason to abandon the batch, since the sources do not
            share configuration.
    """
    try:
        document = fetcher(doi)
    except NoOpenAccessVersion:
        return "no_open_access"
    except FullTextConfigError:
        raise
    except FullTextTransientError as e:
        logger.info("Full text unavailable for %s: %s", doi, e)
        return _failed(paper, e)
    except Exception as e:  # noqa: BLE001 — an optional stage must not fail the run
        logger.warning("Unexpected full-text failure for %s: %s", doi, e)
        return _failed(paper, e)

    if not document.has_text_layer or not document.text.strip():
        return "no_text_layer"

    paper["_full_text_source"] = document.source

    chunks = chunk_document(document, parent_id)
    if not chunks:
        # Extracted text with no recognisable section: the extractor, not OCR.
        return "no_sections"

    records = [
        {
            "chunk_id": c.chunk_id,
            "parent_id": c.parent_id,
            "text": c.text,
            "section": c.section,
            "index": c.index,
            "start": c.start,
            "end": c.end,
            # So `chunk_search` can name the paper: the parent_id is not readable.
            "title": str(paper.get("Title") or ""),
            "doi": doi,
            "year": str(paper.get("Year") or ""),
            "source": document.source,
        }
        for c in chunks
    ]

    try:
        indexed = store.index_chunks(records, collection_name=collection_name)
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not index chunks for %s: %s", doi, e)
        return _failed(paper, e, kind="store")

    if indexed and replace:
        # After the replacement is in the store, and naming what it kept. A delete
        # ordered before the index ran on the old chunks and then left the paper
        # with none at all when the store refused the batch.
        store.delete_chunks(
            parent_id,
            collection_name=collection_name,
            keep_ids=[c["chunk_id"] for c in records],
        )

    return "obtained" if indexed else _failed(paper, "the store refused the batch", kind="store")


def _failed(paper: Dict[str, Any], reason: Any, kind: str = "") -> str:
    """Mark a download as failed, keeping why: the causes need different fixes.

    The kind travels beside the message so the coverage can be counted by cause
    — and so it survives the 300-character truncation, which is the only thing
    the reason used to be.
    """
    paper["_full_text_error"] = " ".join(str(reason).split())[:300]
    paper["_full_text_error_kind"] = kind or _kind_of(reason)
    return "download_failed"


def _kind_of(reason: Any) -> str:
    """Which cause this was, as a value rather than prose."""
    if isinstance(reason, FullTextTransientError):
        return reason.kind
    if isinstance(reason, FullTextConfigError):
        return "config"
    return "unknown"


def _report(
    counters: Mapping[str, int],
    max_papers: int,
    budget: float,
    failure_kinds: Optional[Mapping[str, int]] = None,
) -> None:
    logger.info(
        "Full text: %d obtained, %d without an OA copy, %d failed, "
        "%d without a text layer, %d without usable sections, %d not attempted, "
        "%d already indexed.",
        counters["obtained"], counters["no_open_access"],
        counters["download_failed"], counters["no_text_layer"],
        counters["no_sections"], counters["not_attempted"],
        counters["already_indexed"],
    )
    if failure_kinds:
        # Separately, because they need different fixes and only one is worth
        # retrying: a refusal is not a missing file, and neither is weather.
        logger.info(
            "Of the failures: %s.",
            ", ".join(f"{n} {kind}" for kind, n in sorted(failure_kinds.items())),
        )
    if counters["not_attempted"]:
        # Silence here would read as "there is no OA copy".
        logger.warning(
            "%d papers were not attempted (budget: %d papers / %ds). "
            "Raise settings.fulltext.max_papers or time_budget_seconds.",
            counters["not_attempted"], max_papers, budget,
        )
