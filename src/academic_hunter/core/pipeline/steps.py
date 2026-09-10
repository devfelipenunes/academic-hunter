"""Pipeline step abstraction — each phase of the SLR pipeline is a class.

Keeps ``manager.py`` focused on orchestration while each step owns its
logic, logging, and testability.
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ..nlp.fusion import DEFAULT_STRATEGY, fuse_scores, percentile_ranks

logger = logging.getLogger("academic_hunter.pipeline")


class PipelineStep(ABC):
    """One phase of the SLR pipeline.

    Subclasses implement ``run()`` and can access the hunter via
    ``self.hunter``.
    """

    def __init__(self, hunter: Any) -> None:
        self.hunter = hunter

    @abstractmethod
    def run(self) -> None:
        """Execute this pipeline step."""


class RecomputeRanksStep(PipelineStep):
    """Compute the reported score by fusing the keyword and embedding signals.

    Default fusion (``settings.fusion == "weighted_norm"``):

        score = (α · minmax(kw) + β · minmax(emb)) / (α + β) × 10

    with ``α``/``β`` from ``settings.fusion_weights`` (default 0.7 / 0.3, i.e.
    70% keyword + 30% embedding — the ratio the pipeline's own mode labels have
    always claimed, which the previous formula did not actually implement).

    The previous rule, still available as ``settings.fusion == "rank_geometric"``::

        score = sqrt(rank_sem × rank_kw) × 10

    Both signals are min-max normalised to [0, 1] and combined as a *weighted
    sum*, so a paper strong on one signal is not dragged down by being mid-pack
    on the other. Nothing is lost: the raw magnitudes survive the normalisation,
    only the offset and scale are removed. ``_rank_kw`` and ``_rank_sem`` are
    recorded per paper for diagnostics.

    This step is the **sole writer** of ``Relevance_Score``. Ingest records the
    ablation-dependent inclusion score under ``_hybrid_score`` instead, so that
    one key never carries two different scales. Everything downstream — the
    final threshold filter, exporters, PRISMA and the ChromaDB payload — reads
    the value written here.
    """

    def run(self) -> None:
        results = self.hunter.consolidated_results
        if not results:
            return

        papers_list = list(results.values())
        n = len(papers_list)

        kw_list, sem_list = [], []
        for p in papers_list:
            kw = p.get("_kw_score")
            if kw is None:
                kw = self.hunter.scorer.calculate_score(
                    p.get("Title", ""), p.get("Abstract", ""), p.get("Citations", 0))
                p["_kw_score"] = kw
            kw_list.append(kw)

            sem = p.get("_sem_score")
            if sem is None and self.hunter.semantic_screener is not None:
                sem_config = self.hunter.config.screener_config()
                sem = self.hunter.semantic_screener.evaluate(p, sem_config)
                p["_sem_score"] = round(sem, 4)
            sem_list.append(sem if sem is not None else 0.0)

        strategy = str(self.hunter.settings.get("fusion", DEFAULT_STRATEGY))
        if strategy not in ("weighted_norm", "rank_geometric"):
            logger.warning(
                "Unknown fusion strategy %r; falling back to %r.",
                strategy, DEFAULT_STRATEGY,
            )
            strategy = DEFAULT_STRATEGY

        final_scores = fuse_scores(
            kw_list, sem_list,
            strategy=strategy,
            weights=self.hunter.settings.get("fusion_weights"),
        )

        # Percentile ranks are recorded for diagnostics regardless of strategy,
        # since they are what the superseded rule used and what the experiment
        # scripts compare against.
        rank_kw = percentile_ranks(kw_list)
        rank_sem = percentile_ranks(sem_list)

        for i, slug in enumerate(results.keys()):
            results[slug]["Relevance_Score"] = round(float(final_scores[i]), 1)
            results[slug]["_rank_kw"] = round(rank_kw[i], 4)
            results[slug]["_rank_sem"] = round(rank_sem[i], 4)

        min_score = self.hunter.settings.get('min_relevance_score', 5.0)
        n_after = sum(1 for p in results.values() if p.get("Relevance_Score", 0) >= min_score)
        with self.hunter.lock:
            self.hunter.state.stats["included_final"] = n_after
            self.hunter.state.stats["excluded_score"] = n - n_after

        logger.info("Re-ranked %d papers (%s). %d pass threshold.", n, strategy, n_after)


class IndexResultsStep(PipelineStep):
    """Accumulate consolidated results into ChromaDB for semantic search."""

    def run(self) -> None:
        store = getattr(self.hunter.pipeline, "vector_store", None)
        if store is None:
            logger.info("Vector store not available, skipping semantic indexing.")
            return

        papers = list(self.hunter.consolidated_results.values())
        if not papers:
            logger.info("No papers to index.")
            return

        success = store.index_papers(papers)
        if success:
            logger.info("Indexed %d new papers. ChromaDB accumulates across runs.", len(papers))


class AutoExportObsidianStep(PipelineStep):
    """Auto-export elite report to Obsidian vault if configured.

    The write itself is delegated to ``hunter.obsidian_export``, a callable the
    composition root supplies. This step used to import ``export_to_obsidian``
    from ``interfaces.mcp.tools`` — the domain reaching into the interface layer,
    the most serious of the boundary violations.
    """

    def __init__(self, hunter: Any, timestamp: str = "") -> None:
        super().__init__(hunter)
        self.timestamp = timestamp

    def run(self) -> None:
        obsidian_path = self.hunter.config.settings.get("obsidian_vault_path", "")
        if not obsidian_path:
            return

        export = getattr(self.hunter, "obsidian_export", None)
        if export is None:
            return

        papers = list(self.hunter.consolidated_results.values())
        if not papers:
            return

        total = len(papers)
        top = sorted(papers, key=lambda p: p.get("Relevance_Score", 0.0), reverse=True)[:10]

        lines = [f"# Academic Hunter Report — {self.timestamp}\n"]
        lines.append(f"**Total papers found:** {total}\n")
        lines.append(f"**Sources:** {', '.join(self.hunter.connectors.keys())}\n")
        lines.append(f"**Anchors:** {', '.join(self.hunter.anchors.keys())}\n")
        lines.append("\n---\n")
        lines.append("## Top 10 Papers by Relevance Score\n")

        for i, p in enumerate(top, 1):
            title = p.get("Title", "Untitled")
            score = p.get("Relevance_Score", 0.0)
            year = p.get("Year", "N/A")
            source = p.get("Source", "Unknown")
            doi = p.get("DOI", "")
            url = p.get("URL", "")
            lines.append(f"### {i}. {title}\n")
            lines.append(f"- **Score:** {score} | **Year:** {year} | **Source:** {source}\n")
            if doi:
                lines.append(f"- **DOI:** `{doi}`\n")
            if url:
                lines.append(f"- **URL:** {url}\n")
            lines.append("")

        content = "\n".join(lines)

        try:
            result = export(
                topic=f"Academic Hunter Report {self.timestamp}",
                content=content,
                tags=["academic-hunter", "research", "automated"],
                vault_path=obsidian_path,
            )
            logger.info("Obsidian auto-export: %s", result)
        except Exception as e:
            logger.debug("Obsidian auto-export skipped: %s", e)
