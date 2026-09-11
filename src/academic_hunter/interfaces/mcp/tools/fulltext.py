"""Full-text tools: what was obtained, indexing more of it, and searching inside it.

The ingest is ``core.fulltext.ingest`` — the same loop the pipeline step runs.
"""

import csv
import importlib.util
import json
import logging
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from academic_hunter.core.evaluation.qrels import doc_id_for
from academic_hunter.core.fulltext.ingest import STATUSES, ingest_full_text
from academic_hunter.core.infra.config import HunterConfig
from academic_hunter.core.ports.vector_store import ChunkStorePort
from mcp.server.fastmcp import Context

from ._utils import (
    _get_vector_store,
    _latest_run_dir,
    _load_latest_papers,
    _make_hunter,
    run_blocking,
)

logger = logging.getLogger("academic_hunter.mcp.fulltext")

DEFAULT_COLLECTION = "paper_chunks"

PREVIEW_CHARS = 400


def _pypdf_installed() -> bool:
    """Whether the optional ``fulltext`` extra is present.

    Without it the PDF leg extracts nothing, so "0 obtained" would read as "there
    is no open-access copy" when half the chain is switched off.
    """
    try:
        return importlib.util.find_spec("pypdf") is not None
    except (ImportError, ValueError):
        return False


def _statuses_from_dataset(csv_path: Path) -> Optional[Counter]:
    """Per-paper status counts from a run's dataset, or None if it never ran.

    None is not zero: an absent column means the step did not run.
    """
    try:
        with csv_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or "_full_text_status" not in reader.fieldnames:
                return None
            counts: Counter = Counter()
            for row in reader:
                counts[(row.get("_full_text_status") or "").strip() or "(unset)"] += 1
            return counts
    except OSError as e:
        logger.warning("Could not read %s: %s", csv_path, e)
        return None


def _latest_dataset(run_dir: Optional[Path]) -> Optional[Path]:
    if run_dir is None:
        return None
    files = sorted(run_dir.glob("academic_dataset_*.csv"))
    return files[-1] if files else None


def _run_stats(run_dir: Optional[Path]) -> Dict[str, Any]:
    if run_dir is None:
        return {}
    files = sorted(run_dir.glob("run_stats_*.json"))
    if not files:
        return {}
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.warning("Could not read %s: %s", files[-1], e)
        return {}


async def fulltext_status(ctx: Context = None) -> str:
    """How much full text the corpus has, and where it came from.

    Separates what the last run fetched from what the index already held, and
    labels the chunk count as persistent state covering every run.
    """
    await ctx.info("Checking full-text coverage...")

    try:
        cfg = await run_blocking(lambda: HunterConfig().fulltext_config())
    except Exception as e:  # noqa: BLE001 — a missing config must not kill the report
        logger.warning("Could not read the configuration: %s", e)
        cfg = {}
    run_dir = await run_blocking(_latest_run_dir)
    dataset = _latest_dataset(run_dir)
    stats = await run_blocking(_run_stats, run_dir)
    per_paper = await run_blocking(_statuses_from_dataset, dataset) if dataset else None

    store = _get_vector_store()
    chunks = 0
    if store is not None:
        collection = await run_blocking(store.collection_stats, DEFAULT_COLLECTION)
        chunks = collection.get("count", 0)

    lines = ["# Full-text coverage\n"]
    enabled = "unknown (no readable config)" if not cfg else ("yes" if cfg.get("enabled") else "no")
    lines.append(f"**Step enabled in config:** {enabled} (`settings.fulltext.enabled`)\n")
    has_pypdf = _pypdf_installed()
    lines.append(
        f"**`pypdf` installed:** {'yes' if has_pypdf else 'no'}"
        + (
            "\n"
            if has_pypdf
            else " — the PDF leg is off; only Europe PMC can deliver text "
            "(`pip install academic-hunter[fulltext]`)\n"
        )
    )
    lines.append(f"**Chunks in `{DEFAULT_COLLECTION}`:** {chunks} "
                 "_(persistent — every run, not this one)_\n")

    if run_dir is None:
        lines.append(
            "\nNo run found under `results/`. Run `run_search` first, or index "
            "full text directly with `index_fulltext`.\n"
        )
        return "\n".join(lines)

    lines.append(f"\n**Last run:** `{run_dir.name}`\n")

    counters = (stats.get("full_text") or {})
    if counters:
        lines.append("\nCounters from `run_stats`:\n")
        for status in STATUSES:
            if status in counters:
                lines.append(f"- {status}: {counters[status]}")
        lines.append("")
    if per_paper is None:
        lines.append(
            "\n⚠️  The run's dataset has no `_full_text_status` column, so the "
            "full-text step **did not run** in this run — this is not the same "
            "as finding no open-access copies. Enable `settings.fulltext.enabled` "
            "or call `index_fulltext`.\n"
        )
    else:
        lines.append("\nPer paper, from the run's dataset:\n")
        for status, count in sorted(per_paper.items()):
            lines.append(f"- {status}: {count}")
        lines.append("")

    return "\n".join(lines)


async def index_fulltext(
    force: bool = False, limit: int = 0, ctx: Context = None
) -> str:
    """Fetch, chunk and index the full text of the latest run's papers.

    Unlike the pipeline step this does not require ``settings.fulltext.enabled``,
    and papers already indexed are skipped unless ``force``.

    Args:
        force: Re-fetch and re-index papers that already have chunks.
        limit: Cap how many papers to attempt, for a smoke run.
    """
    await ctx.info("Indexing full text for the latest run...")

    papers = await run_blocking(_load_latest_papers)
    if not papers:
        return (
            "No papers found. Run `run_search` first, or point the tool at a run "
            "that produced a dataset."
        )

    store = _get_vector_store()
    if store is None:
        await ctx.error("Could not initialize vector store")
        return "Error: could not initialize the vector store."
    if not isinstance(store, ChunkStorePort):
        return (
            "Error: the configured vector store cannot hold chunks, so full text "
            "cannot be indexed."
        )

    hunter = await run_blocking(_make_hunter)
    fetcher = getattr(hunter, "full_text_fetcher", None)
    if fetcher is None:
        return "Error: no full-text fetcher is wired."

    cfg = hunter.config.fulltext_config()
    max_papers = limit or cfg["max_papers"]

    await ctx.report_progress(0, 1, f"Fetching full text for up to {max_papers} papers...")
    counters = await run_blocking(
        ingest_full_text,
        papers,
        fetcher,
        store,
        {**cfg, "max_papers": max_papers},
        force=force,
    )
    await ctx.report_progress(1, 1, "Done")

    if not _pypdf_installed():
        await ctx.warning("pypdf is not installed; only Europe PMC could deliver text.")

    lines = ["# Full-text indexing\n", f"Papers considered: {len(papers)}"]
    for status in STATUSES:
        if counters.get(status):
            lines.append(f"- {status}: {counters[status]}")
    if counters.get("already_indexed") and not force:
        lines.append(
            "\nThose papers were skipped because their chunks are already "
            "indexed. Pass `force=true` to fetch them again."
        )
    if counters.get("not_attempted"):
        lines.append(
            "\nThe rest were not attempted — raise `limit` or "
            "`settings.fulltext.max_papers` / `time_budget_seconds`."
        )

    await ctx.info(f"Full text: {counters.get('obtained', 0)} obtained")
    return "\n".join(lines)


def _group_hits(hits: List[Dict[str, Any]], per_paper: int, top_k: int) -> List[Dict[str, Any]]:
    """Group chunks under their paper, best paper first, ``per_paper`` each.

    The caller over-fetches: ten chunks are easily two papers.
    """
    by_parent: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for hit in hits:
        by_parent[hit.get("parent_id") or ""].append(hit)

    groups = []
    for parent_id, group in by_parent.items():
        group.sort(key=lambda h: (-float(h.get("relevance") or 0.0), h.get("index") or 0))
        best = group[0]
        groups.append({
            "parent_id": parent_id,
            "title": best.get("title") or "",
            "doi": best.get("doi") or "",
            "year": best.get("year") or "",
            "source": best.get("source") or "",
            "relevance": float(best.get("relevance") or 0.0),
            "chunks": group[:per_paper],
        })

    groups.sort(key=lambda g: -g["relevance"])
    return groups[:top_k]


def _resolve_titles(groups: List[Dict[str, Any]]) -> None:
    """Name the papers whose chunks carry no title.

    Only the fallback costs anything: current chunks carry the title. Older ones
    resolve through the run dataset, using the same id scheme the ingest used —
    a map identity, not a fuzzy match.
    """
    missing = [g for g in groups if not g["title"] and g["parent_id"]]
    if not missing:
        return

    by_id = {}
    for paper in _load_latest_papers():
        title = str(paper.get("Title") or "")
        doi = str(paper.get("DOI") or "")
        if title or doi:
            by_id[doc_id_for(title, doi)] = title

    for group in missing:
        group["title"] = by_id.get(group["parent_id"], "")


async def chunk_search(
    query: str,
    top_k: int = 10,
    per_paper: int = 3,
    collection_name: str = DEFAULT_COLLECTION,
    ctx: Context = None,
) -> str:
    """Search inside the full text; returns passages grouped by paper.

    Answers what an abstract cannot — which dataset, how many annotators.

    Args:
        query: What to look for, in natural language.
        top_k: How many papers to return.
        per_paper: How many passages to show per paper.
        collection_name: Chunks collection; the evaluation has its own.
    """
    await ctx.info(f"Searching chunks for: {query}")

    store = _get_vector_store()
    if store is None:
        return "Error: could not initialize the vector store."
    if not isinstance(store, ChunkStorePort):
        return "Error: the configured vector store cannot hold chunks."

    hits = await run_blocking(
        store.query_chunks, query, top_k * per_paper, collection_name
    )
    if not hits:
        return (
            f"No chunks in `{collection_name}`. Index full text first with "
            "`index_fulltext`."
        )

    groups = _group_hits(hits, per_paper=per_paper, top_k=top_k)
    await run_blocking(_resolve_titles, groups)

    lines = [f"# Passages for: {query}\n", f"{len(groups)} paper(s), {len(hits)} passage(s) considered\n"]
    for group in groups:
        label = group["title"] or f"{group['parent_id']} _(derived id, no title on record)_"
        meta = " · ".join(
            part for part in (
                group["doi"],
                str(group["year"]) if group["year"] else "",
                group["source"],
            ) if part
        )
        lines.append(f"\n## {label}")
        if meta:
            lines.append(f"_{meta}_")
        for chunk in group["chunks"]:
            text = " ".join(str(chunk.get("text") or "").split())
            lines.append(
                f"\n**[{chunk.get('section') or 'body'} · chunk "
                f"{chunk.get('index')} · chars {chunk.get('start')}–{chunk.get('end')} · "
                f"relevance {chunk.get('relevance')}]**\n"
                f"{text[:PREVIEW_CHARS]}{'…' if len(text) > PREVIEW_CHARS else ''}"
            )

    await ctx.info(f"Returned {len(groups)} papers")
    return "\n".join(lines)
