import threading
from typing import Dict, Any, List
from ..infra import SearchState, HunterConfig
from ..nlp import AcademicScorer
from ..models import Paper
from .resolvers import PaperResolver

class PaperProcessor:
    """Handles duplicate checking, temporal filtering, anchor matching, scoring, and metadata merging for mined papers."""
    def __init__(self, state: SearchState, scorer: AcademicScorer, config: HunterConfig, connectors: Dict[str, Any], lock: threading.RLock, semantic_screener=None):
        self.state = state
        self.scorer = scorer
        self.config = config
        self.connectors = connectors
        self.lock = lock
        self.semantic_screener = semantic_screener
        self.resolver = PaperResolver(state, scorer, config, connectors, lock, semantic_screener)

    def process(self, paper: Dict[str, Any], anchor_cat: str, tech_cat: str, anchor_list: List[str], tech_list: List[str]):
        """Deduplicates, scores, filters, and merges metadata for mined papers (thread-safe)."""
        source = paper.get('Source', 'Unknown')

        with self.lock:
            self.state.stats["identified"][source] = self.state.stats["identified"].get(source, 0) + 1

        title = paper.get('Title', '').strip()
        if not title:
            return

        doi_clean = Paper.normalize_doi(paper.get('DOI') or "")

        # Decide new-vs-duplicate and, when new, claim the identifiers in the
        # *same* critical section. Checking under one lock acquisition and
        # recording under another left a window in which two threads both
        # concluded "new" for the same paper and registered it twice.
        with self.lock:
            dedup_id = self.scorer.generate_slug(title)
            is_duplicate = dedup_id in self.state.seen_ids
            if not is_duplicate and doi_clean and doi_clean in self.state.seen_dois:
                is_duplicate = True
                dedup_id = self.state.doi_to_slug.get(doi_clean, dedup_id)

            if is_duplicate:
                self.state.stats["duplicates_removed"] += 1
                # Read under the same lock: the dict is mutated by other threads.
                existing = self.state.consolidated_results.get(dedup_id)
            else:
                self.state.seen_ids.add(dedup_id)
                if doi_clean:
                    self.state.seen_dois.add(doi_clean)
                    self.state.doi_to_slug[doi_clean] = dedup_id

        # The expensive work (scoring, merging, connector lookups) stays outside
        # the lock; the claim above is what makes that safe.
        if is_duplicate:
            if existing is not None:
                self.resolver.resolve_existing_duplicate(existing, paper, anchor_cat, tech_cat, source)
            else:
                self.resolver.resolve_excluded_duplicate(paper, dedup_id, title, doi_clean, tech_cat, tech_list, source)
            return

        self.resolver.register_new_paper(paper, dedup_id, title, doi_clean, tech_cat, tech_list, source)
