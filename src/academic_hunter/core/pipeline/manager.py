import logging
import time
import threading
from typing import Dict, List, Any, Optional

logger = logging.getLogger("academic_hunter")


class SearchPipeline:
    """Manages concurrent worker execution, pacing delays, abstract enrichment, and document export pipeline."""
    def __init__(self, hunter):
        self.hunter = hunter
        self._vector_store = None

    @property
    def vector_store(self):
        """Lazy-init ChromaDB vector store for RAG."""
        if self._vector_store is None:
            try:
                from ...plugins.vector_stores import ChromaVectorStore
                self._vector_store = ChromaVectorStore(
                    db_dir=str(self.hunter.output_dir.parent / ".academic_hunter" / "chroma_db")
                )
            except Exception as e:
                logger.warning(f"Could not initialize vector store: {e}")
                self._vector_store = None
        return self._vector_store

    def _index_results(self):
        """Accumulate consolidated results into ChromaDB for semantic search.

        Uses upsert (dedup by DOI/title hash), so papers accumulate across runs
        without duplicates. Previous behavior cleared the collection — now we
        preserve history.
        """
        store = self.vector_store
        if store is None:
            logger.info("Vector store not available, skipping semantic indexing.")
            return

        papers = list(self.hunter.consolidated_results.values())
        if not papers:
            logger.info("No papers to index.")
            return

        # Accumulate — upsert handles dedup by DOI/title hash
        success = store.index_papers(papers)
        if success:
            logger.info(f"✅ Indexed {len(papers)} new papers. ChromaDB accumulates across runs.")

    def _recompute_ranks(self):
        """Re-rank all papers using multiplicative rank normalization.

        Converts raw keyword and Weight-Bleeding scores to percentil ranks,
        then computes the final score as the geometric mean of both ranks:

            score = sqrt(rank_sem × rank_kw) × 10

        This is superior to additive blending (a×kw + b×sem) because:
        - Paper must perform well in BOTH signals (geometric, not arithmetic)
        - If either signal is zero, score is zero (no false positives)
        - No arbitrary weight ratio (70/30, 50/50, etc.)
        - Natural scaling: both ranks are always [0, 1]
        """
        results = self.hunter.consolidated_results
        if not results:
            return

        papers_list = list(results.values())
        n = len(papers_list)
        if n < 2:
            return

        import numpy as np

        # Compute raw scores for ALL papers (handle missing _kw_score/_sem_score)
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
            """Convert scores to percentil ranks (0 to 1)."""
            sorted_idx = np.argsort(arr)
            ranks = np.empty_like(sorted_idx, dtype=float)
            ranks[sorted_idx] = np.arange(n) / max(n - 1, 1)
            return ranks

        rank_kw = rank(kw_scores)
        rank_sem = rank(sem_scores)

        # Geometric mean: sqrt(rank_sem × rank_kw) × 10
        # Paper must score in BOTH dimensions or result is pulled toward zero
        final_scores = np.sqrt(rank_sem * rank_kw) * 10.0

        for i, slug in enumerate(results.keys()):
            results[slug]["Relevance_Score"] = round(float(final_scores[i]), 1)

        # Update stats after re-ranking
        min_score = self.hunter.settings.get('min_relevance_score', 5.0)
        n_after = sum(1 for p in results.values() if p.get("Relevance_Score", 0) >= min_score)
        with self.hunter.lock:
            self.hunter.state.stats["included_final"] = n_after
            self.hunter.state.stats["excluded_score"] = n - n_after

        logger.info(f"📊 Re-ranked {n} papers (geom. mean). {n_after} pass threshold.")

    def _api_worker(self, source_name: str, fetch_func=None, limit_per_source: int = 100):
        connector = self.hunter.connectors.get(source_name)
        if not connector:
            return

        is_keyword_only = getattr(connector, "is_keyword_only", False)

        if fetch_func is not None:
            fetch_fn = fetch_func
        else:
            suffix = getattr(connector, "fetch_suffix", source_name.lower().replace(" ", "_"))
            method_name = f"fetch_{suffix}"
            fetch_fn = getattr(self.hunter, method_name, None)
            if not fetch_fn:
                fetch_fn = connector.fetch

        for anchor_cat, anchor_list in self.hunter.anchors.items():
            if is_keyword_only:
                tech_list = self.hunter.config.keyword_only_terms
                try:
                    results = fetch_fn(anchor_list, tech_list, limit=limit_per_source)
                    if results:
                        for paper in results:
                            consolidated_cat = self.hunter.config.keyword_only_category
                            self.hunter._process_paper(paper, anchor_cat, consolidated_cat, anchor_list, tech_list)
                except Exception as e:
                    logger.error(f"[{source_name} Worker] {e}")

                time.sleep(1.0)
            else:
                for tech_cat, tech_list in self.hunter.tech_strings.items():
                    try:
                        results = fetch_fn(anchor_list, tech_list, limit=limit_per_source)
                        if results:
                            for paper in results:
                                self.hunter._process_paper(paper, anchor_cat, tech_cat, anchor_list, tech_list)
                    except Exception as e:
                        logger.error(f"[{source_name} Worker] {e}")

                    time.sleep(1.0)

    def run(self, limit_per_source: int = 100):
        logger.info("🚀 Initializing Multi-Threaded Academic Hunter V2 Pipeline...")
        timestamp = time.strftime("%Y%m%d_%H%M%S")

        self.hunter.state.reset(list(self.hunter.connectors.keys()))
        self.hunter.last_request_time = time.time()

        threads = []
        for src, conn in self.hunter.connectors.items():
            domain = getattr(conn, "domain", "")
            if domain in self.hunter.blocked_sources:
                continue
            t = threading.Thread(target=self._api_worker, args=(src, None, limit_per_source))
            t.daemon = True
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Rank-based scoring: recompute scores using percentil normalization
        self._recompute_ranks()

        elapsed = round(time.time() - self.hunter.last_request_time, 2)
        logger.info(f"⏱️ Mining completed in {elapsed} seconds.")

        self.hunter.enrich_missing_abstracts()

        self.hunter.export_results(timestamp)
        self.hunter.generate_prisma_report(timestamp)

        final_qualifiers = {
            slug: paper for slug, paper in self.hunter.consolidated_results.items()
            if paper.get("Relevance_Score", 0.0) >= self.hunter.settings.get('min_relevance_score', 5.0)
        }

        self.hunter.consolidated_results = final_qualifiers

        self.hunter.export_results(timestamp)

        # Auto-index for RAG
        self._index_results()

        # Auto-export to Obsidian if configured
        self._auto_export_to_obsidian(timestamp)

        logger.info("💎 PIPELINE FINISHED!")
        logger.info("📊 PRISMA STATS:")
        logger.info(f"   - Identified: {self.hunter.stats['identified']}")
        logger.info(f"   - Duplicates Removed: {self.hunter.stats['duplicates_removed']}")
        logger.info(f"   - Excluded (Publication Year): {self.hunter.stats['excluded_year']}")
        logger.info(f"   - Excluded (No Industry Anchors): {self.hunter.stats['excluded_anchors']}")
        logger.info(f"   - Excluded (Low Relevance Score): {self.hunter.stats['excluded_technical_score']}")
        logger.info(f"   - Final Included: {self.hunter.stats['included_final']}")

        import os
        return os.path.join(self.hunter.output_dir, f"RELATORIO_ELITE_{timestamp}.md")

    def _auto_export_to_obsidian(self, timestamp: str):
        """Auto-export elite report to Obsidian vault if configured."""
        obsidian_path = self.hunter.config.settings.get("obsidian_vault_path", "")
        if not obsidian_path:
            return

        try:
            papers = list(self.hunter.consolidated_results.values())
            if not papers:
                return

            # Build a compact summary note
            total = len(papers)
            top = sorted(papers, key=lambda p: p.get("Relevance_Score", 0.0), reverse=True)[:10]

            lines = [f"# Academic Hunter Report — {timestamp}\n"]
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

            from ...interfaces.mcp.tools.obsidian import export_to_obsidian
            result = export_to_obsidian(
                topic=f"Academic Hunter Report {timestamp}",
                content=content,
                tags=["academic-hunter", "research", "automated"],
            )
            logger.info(f"Obsidian auto-export: {result}")
        except Exception as e:
            logger.debug(f"Obsidian auto-export skipped: {e}")
