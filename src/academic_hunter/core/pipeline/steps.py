"""Pipeline step abstraction — each phase of the SLR pipeline is a class.

Keeps ``manager.py`` focused on orchestration while each step owns its
logic, logging, and testability.
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

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
    """Re-rank all papers using multiplicative rank normalization.

    Converts raw keyword and Weight-Bleeding scores to percentil ranks,
    then computes the final score as the geometric mean of both ranks:

        score = sqrt(rank_sem × rank_kw) × 10
    """

    def run(self) -> None:
        results = self.hunter.consolidated_results
        if not results:
            return

        papers_list = list(results.values())
        n = len(papers_list)
        if n < 2:
            return

        import numpy as np

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
                sem_config = {
                    "anchors": self.hunter.config.anchors,
                    "technical_strings": self.hunter.config.tech_strings,
                    "technical_weights": self.hunter.config.tech_weights,
                }
                sem = self.hunter.semantic_screener.evaluate(p, sem_config)
                p["_sem_score"] = round(sem, 4)
            sem_list.append(sem if sem is not None else 0.0)
        kw_scores = np.array(kw_list)
        sem_scores = np.array(sem_list)

        def rank(arr):
            sorted_idx = np.argsort(arr)
            ranks = np.empty_like(sorted_idx, dtype=float)
            ranks[sorted_idx] = np.arange(n) / max(n - 1, 1)
            return ranks

        rank_kw = rank(kw_scores)
        rank_sem = rank(sem_scores)

        final_scores = np.sqrt(rank_sem * rank_kw) * 10.0

        for i, slug in enumerate(results.keys()):
            results[slug]["Relevance_Score"] = round(float(final_scores[i]), 1)

        min_score = self.hunter.settings.get('min_relevance_score', 5.0)
        n_after = sum(1 for p in results.values() if p.get("Relevance_Score", 0) >= min_score)
        with self.hunter.lock:
            self.hunter.state.stats["included_final"] = n_after
            self.hunter.state.stats["excluded_score"] = n - n_after

        logger.info("Re-ranked %d papers (geom. mean). %d pass threshold.", n, n_after)


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
    """Auto-export elite report to Obsidian vault if configured."""

    def __init__(self, hunter: Any, timestamp: str = "") -> None:
        super().__init__(hunter)
        self.timestamp = timestamp

    def run(self) -> None:
        obsidian_path = self.hunter.config.settings.get("obsidian_vault_path", "")
        if not obsidian_path:
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
            from ...interfaces.mcp.tools.obsidian import export_to_obsidian
            result = export_to_obsidian(
                topic=f"Academic Hunter Report {self.timestamp}",
                content=content,
                tags=["academic-hunter", "research", "automated"],
            )
            logger.info("Obsidian auto-export: %s", result)
        except Exception as e:
            logger.debug("Obsidian auto-export skipped: %s", e)
