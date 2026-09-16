import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any
from ..models import Paper
from ..infra import SearchState

logger = logging.getLogger("academic_hunter")


class AbstractEnricher:
    """Enriches papers that qualify but have empty abstracts by querying their DOI via registered connector APIs."""
    def __init__(self, connectors: Dict[str, Any], state: SearchState, lock: threading.RLock):
        self.connectors = connectors
        self.state = state
        self.lock = lock

    def fetch_abstract_by_doi(self, doi: str) -> str:
        if not doi:
            return ""
        doi_clean = Paper.normalize_doi(doi)

        # 1. Gather all connectors supporting DOI resolution, sorted by priority (descending)
        resolving_connectors = []
        for connector in self.connectors.values():
            priority = getattr(connector, "resolve_priority", 0)
            if priority > 0:
                resolving_connectors.append((priority, connector))

        resolving_connectors.sort(key=lambda x: x[0], reverse=True)

        # 2. Try resolving using sorted connectors
        for _, connector in resolving_connectors:
            try:
                abstract = connector.resolve_abstract_by_doi(doi_clean)
                if abstract:
                    return abstract
            except Exception as e:
                logger.debug(f"[{connector.__class__.__name__}] Error resolving DOI {doi_clean}: {e}")

        return ""

    def enrich(self):
        logger.info("🔍 Enriching missing abstracts for qualified papers...")
        with self.lock:
            to_enrich = []
            for slug, paper in self.state.consolidated_results.items():
                abstract = paper.get("Abstract") or ""
                if not abstract.strip() and paper.get("DOI"):
                    to_enrich.append((slug, paper))

        enriched_count = 0
        if not to_enrich:
            logger.info("✅ Abstract enrichment complete. Enriched 0 papers.")
            return

        def task(slug, paper):
            doi = paper.get("DOI")
            abstract = self.fetch_abstract_by_doi(doi)
            return slug, paper, abstract

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(task, slug, paper) for slug, paper in to_enrich]
            for future in as_completed(futures):
                try:
                    slug, paper, abstract = future.result()
                    if abstract:
                        with self.lock:
                            paper["Abstract"] = abstract
                            # Deliberately does NOT write Relevance_Score. Scoring
                            # is owned by the pipeline (validate_and_score, then
                            # RecomputeRanksStep); writing a raw keyword score
                            # here mixed scales within one collection.
                            # Invalidate the cached component scores instead, so
                            # the scoring step recomputes them over the now
                            # complete text — the validator had scored this paper
                            # against an empty abstract.
                            paper["_kw_score"] = None
                            paper["_sem_score"] = None
                            paper["_abstract_enriched"] = True
                            logger.info(f"Enriched '{paper.get('Title')[:40]}...'")
                            enriched_count += 1
                except Exception as e:
                    logger.error(f"Enrichment error: {e}")

        logger.info(f"✅ Abstract enrichment complete. Enriched {enriched_count} papers.")
