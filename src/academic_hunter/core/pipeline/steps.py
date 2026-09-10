"""Pipeline step abstraction — each phase of the SLR pipeline is a class.

Keeps ``manager.py`` focused on orchestration while each step owns its
logic, logging, and testability.
"""

import logging
import math
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ..nlp.bm25 import BM25
from ..nlp.fusion import DEFAULT_STRATEGY, fuse_scores, percentile_ranks
from ..nlp.reranker import rerank_config, rerank_scores, rerank_texts

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
    """Compute the reported score by fusing a sparse and a dense signal.

    Two modes, decided by whether the configuration names a **ranking query**.

    **Without a query** (the default), the sparse signal is the domain-term
    count — a weighted tally of the configured anchor and technical terms. It
    answers "does this paper look like the domain?" and never sees a question,
    which is why every strategy measured without one turned out to be
    query-independent and why the best of them depended on the topic rather
    than on the question.

    **With ``settings.ranking_query``**, the sparse signal becomes BM25 over
    that query, computed across the collected papers. Having an actual question
    is what moved nDCG@10 from 0.28 to 0.67 on the judged collection — far more
    than any change of scoring rule achieved.

    Fusion (``settings.fusion == "weighted_norm"``, the default)::

        score = (α · minmax(sparse) + β · minmax(emb)) / (α + β) × 10

    with ``α``/``β`` from ``settings.fusion_weights``. Defaults are 0.7 / 0.3
    without a query — the ratio the pipeline's own mode labels always claimed
    and the old formula did not implement — and 1.0 / 0.0 with one, because
    adding the embedding measured monotonically worse there (90/10 0.6558,
    70/30 0.6221, 50/50 0.5638, against 0.6728 for BM25 alone).

    The superseded rule remains available as ``settings.fusion ==
    "rank_geometric"``::

        score = sqrt(rank_sparse × rank_emb) × 10

    Both signals are min-max normalised and combined as a *weighted sum*, so a
    paper strong on one signal is not dragged down by being mid-pack on the
    other — the property the rank-geometric rule lacked.

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

        # A configured ranking query switches the sparse signal from the
        # domain-term count to BM25 over that query. The domain count answers
        # "does this paper look like the domain?" — it never sees a question,
        # which is why every strategy measured without one turned out to be
        # query-independent and why the best of them depended on the topic
        # rather than on the question.
        ranking_query = str(self.hunter.settings.get("ranking_query", "") or "").strip()
        sparse_list, weights = kw_list, self.hunter.settings.get("fusion_weights")

        if ranking_query:
            index = BM25([
                f"{p.get('Title', '')} {p.get('Abstract', '')}" for p in papers_list
            ])
            sparse_list = index.score(ranking_query)
            for i, slug in enumerate(results.keys()):
                results[slug]["_bm25_score"] = round(float(sparse_list[i]), 4)

            if weights is None:
                # Measured on the judged collection: BM25 alone scores 0.6728
                # nDCG@10, and adding the embedding lowers it monotonically
                # (90/10 0.6558, 70/30 0.6221, 50/50 0.5638). So the default
                # when a query is present is BM25 alone. Pass fusion_weights
                # explicitly to override.
                weights = {"keyword": 1.0, "embedding": 0.0}

            logger.info("Ranking against the configured query (BM25).")

        final_scores = fuse_scores(
            sparse_list, sem_list,
            strategy=strategy,
            weights=weights,
        )

        # Optional second stage, opt-in via `settings.rerank`. Runs inside this
        # step rather than as a step of its own so that `Relevance_Score` keeps
        # a single writer — see the class docstring.
        final_scores = self._apply_rerank(
            final_scores, papers_list, ranking_query
        )

        # Percentile ranks are recorded for diagnostics regardless of strategy,
        # since they are what the superseded rule used and what the experiment
        # scripts compare against.
        rank_kw = percentile_ranks(sparse_list)
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

    def _apply_rerank(
        self,
        final_scores: List[float],
        papers_list: List[Any],
        ranking_query: str,
    ) -> List[float]:
        """Rerank the head of the ranking with a cross-encoder. Never raises.

        A second stage over the top ``settings.rerank.top_n`` documents. The
        cross-encoder reads ``(query, document)`` as a pair, which the
        first-stage signals cannot do — BM25 matches terms, the embedding
        compares against a domain centroid — and it is far more accurate for it.
        At ~214 ms per pair on CPU it can afford to look at a head, not a
        corpus, which is what bounds ``top_n``.

        Measured on the judged collection, nDCG@10 goes 0.6728 → 0.7668 at
        ``top_n=20``, winning on both topics; the oracle rerank of the whole
        pool reaches 0.7916, so the head captures 97% of the ceiling. Contrast
        the bi-encoder embedding, which *lowers* nDCG as its weight grows — the
        two signals are not interchangeable and only measurement separates them.

        Returns scores with only the reranked head redistributed; see
        :func:`~academic_hunter.core.nlp.reranker.rerank_scores` for the rule.
        Every failure path returns ``final_scores`` untouched: an optional
        enhancement that breaks a run is worse than one that is absent.
        """
        cfg = rerank_config(self.hunter.settings)
        if not cfg["enabled"]:
            return final_scores

        # The cross-encoder scores a (query, document) pair, so without a query
        # there is no pair to score. BM25 at least matches terms against a
        # domain vocabulary; this model has nothing to read. Configuring the
        # rerank without a query is inert, not fatal.
        if not ranking_query:
            logger.warning(
                "settings.rerank.enabled is true but settings.ranking_query is "
                "empty — the cross-encoder has no query to pair documents with. "
                "Skipping the rerank."
            )
            return final_scores

        n = len(papers_list)
        top_n = min(cfg["top_n"], n)
        if top_n < 2:
            return final_scores

        head = sorted(range(n), key=lambda i: (-final_scores[i], i))[:top_n]
        # The same representation the BM25 index above is built on, so both
        # query-aware signals read the same text.
        texts = [
            f"{papers_list[i].get('Title', '')} {papers_list[i].get('Abstract', '')}"
            for i in head
        ]

        try:
            scores = rerank_texts(
                ranking_query,
                texts,
                model_name=cfg["model"],
                max_length=cfg["max_length"],
            )
        except Exception as e:  # noqa: BLE001 — an optional stage must not fail the run
            logger.warning(
                "Cross-encoder rerank failed (%s); keeping the fused ranking.", e
            )
            return final_scores

        if scores is None:
            logger.info("Cross-encoder unavailable; keeping the fused ranking.")
            return final_scores

        if any(not math.isfinite(s) for s in scores):
            # A NaN compares false against everything, so it would sort to an
            # arbitrary position and scramble the head without saying so.
            logger.warning(
                "Cross-encoder returned a non-finite score; keeping the fused ranking."
            )
            return final_scores

        order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))

        for position, i in enumerate(order, 1):
            paper = papers_list[head[i]]
            paper["_rerank_score"] = round(scores[i], 4)
            paper["_rerank_rank"] = position

        with self.hunter.lock:
            self.hunter.state.stats["reranked"] = len(order)

        logger.info(
            "Cross-encoder reranked the top %d of %d papers.", top_n, n
        )
        return rerank_scores(final_scores, [head[i] for i in order])


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
