import logging
import time
import threading
from typing import Dict, List, Any

logger = logging.getLogger("academic_hunter")


class SearchPipeline:
    """Manages concurrent worker execution, pacing delays, abstract enrichment, and document export pipeline."""
    def __init__(self, hunter):
        self.hunter = hunter

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

        self.hunter.enrich_missing_abstracts()

        self.hunter.export_results(timestamp)
        self.hunter.generate_prisma_report(timestamp)

        final_qualifiers = {
            slug: paper for slug, paper in self.hunter.consolidated_results.items()
            if paper.get("Relevance_Score", 0.0) >= self.hunter.settings.get('min_relevance_score', 5.0)
        }

        self.hunter.consolidated_results = final_qualifiers

        self.hunter.export_results(timestamp)

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
