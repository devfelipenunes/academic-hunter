import logging
import threading
import time

from .steps import (
    AutoExportObsidianStep,
    IndexResultsStep,
    IngestFullTextStep,
    RecomputeRanksStep,
)

logger = logging.getLogger("academic_hunter")


class SearchPipeline:
    """Manages concurrent worker execution, pacing delays, abstract enrichment, and document export pipeline."""
    def __init__(self, hunter):
        self.hunter = hunter
        self._vector_store = None

    @property
    def vector_store(self):
        """Lazy-init the vector store for RAG.

        The concrete store comes from ``hunter.vector_store_factory``, which the
        composition root supplies. This module used to import ``ChromaVectorStore``
        directly, coupling the domain to one adapter.
        """
        if self._vector_store is None:
            factory = getattr(self.hunter, "vector_store_factory", None)
            if factory is None:
                logger.info("No vector store factory configured, skipping RAG indexing.")
                return None
            try:
                db_dir = self.hunter.output_dir.parent / ".academic_hunter" / "chroma_db"
                self._vector_store = factory(db_dir)
            except Exception as e:
                logger.warning(f"Could not initialize vector store: {e}")
                self._vector_store = None
        return self._vector_store

    def _index_results(self):
        """Accumulate consolidated results into ChromaDB for semantic search.

        Delegates to IndexResultsStep for implementation.
        """
        IndexResultsStep(self.hunter).run()

    def _recompute_ranks(self):
        """Re-rank all papers using multiplicative rank normalization.

        Delegates to RecomputeRanksStep for implementation.
        """
        RecomputeRanksStep(self.hunter).run()

    def _ingest_full_text(self):
        """Fetch and index full text for the qualified papers.

        Opt-in (`settings.fulltext.enabled`) and a no-op when it is off, which
        is the default. Delegates to IngestFullTextStep.
        """
        IngestFullTextStep(self.hunter).run()

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

        elapsed = round(time.time() - self.hunter.last_request_time, 2)
        logger.info(f"⏱️ Mining completed in {elapsed} seconds.")

        # Enrich BEFORE scoring. Enrichment supplies missing abstracts, and the
        # score must be computed over the final text. Running it afterwards
        # overwrote Relevance_Score with a raw keyword value, putting two
        # different scales in the same collection while both were compared
        # against the same min_relevance_score threshold — so enriched papers
        # systematically outranked the rest.
        self.hunter.enrich_missing_abstracts()

        # Rank-based scoring: recompute scores using percentil normalization
        self._recompute_ranks()

        self.hunter.export_results(timestamp)
        self.hunter.generate_prisma_report(timestamp)

        final_qualifiers = {
            slug: paper for slug, paper in self.hunter.consolidated_results.items()
            if paper.get("Relevance_Score", 0.0) >= self.hunter.settings.get('min_relevance_score', 5.0)
        }

        self.hunter.consolidated_results = final_qualifiers

        # Full text, opt-in and off by default. Here — after the threshold
        # filter, before the index — so the downloads are spent on the papers
        # that qualified rather than on everything identified.
        self._ingest_full_text()

        self.hunter.export_results(timestamp)
        # Regenerated: the report above was written before this step could know
        # how many full texts were obtained, and SLR methodology requires that
        # number. Same reason `export_results` is called twice.
        self.hunter.generate_prisma_report(timestamp)

        # Auto-index for RAG
        self._index_results()

        # Auto-export to Obsidian if configured
        self._auto_export_to_obsidian(timestamp)

        # A run whose embedding silently fell back to zeros still finishes and
        # still reports numbers; say so, because those numbers are not
        # comparable to a run with a working model.
        screener = getattr(self.hunter, "semantic_screener", None)
        if screener is not None and getattr(screener, "degraded", False):
            logger.warning(
                "⚠️ Semantic screener ran in ZERO-VECTOR mode: every semantic "
                "score is 0.0. Treat this run's scores as keyword-only."
            )

        logger.info("💎 PIPELINE FINISHED!")
        logger.info("📊 PRISMA STATS:")
        logger.info(f"   - Identified: {self.hunter.stats['identified']}")
        logger.info(f"   - Duplicates Removed: {self.hunter.stats['duplicates_removed']}")
        logger.info(f"   - Excluded (Publication Year): {self.hunter.stats['excluded_year']}")
        logger.info(f"   - Excluded (No Industry Anchors): {self.hunter.stats['excluded_anchors']}")
        logger.info(f"   - Excluded (Low Relevance Score): {self.hunter.stats['excluded_technical_score']}")
        logger.info(f"   - Final Included: {self.hunter.stats['included_final']}")
        if "reranked" in self.hunter.stats:
            logger.info(
                f"   - Reranked (cross-encoder): {self.hunter.stats['reranked']}"
            )

        import os
        return os.path.join(self.hunter.output_dir, f"RELATORIO_ELITE_{timestamp}.md")

    def _auto_export_to_obsidian(self, timestamp: str):
        """Auto-export elite report to Obsidian vault if configured."""
        AutoExportObsidianStep(self.hunter, timestamp=timestamp).run()
