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

    def _check_duplicate(self, title: str, doi_clean: str) -> tuple[bool, str]:
        """Checks if a paper is duplicate by title slug or normalized DOI (thread-safe)."""
        dedup_id = self.scorer.generate_slug(title)
        is_duplicate = False
        with self.lock:
            if dedup_id in self.state.seen_ids:
                is_duplicate = True
            elif doi_clean and doi_clean in self.state.seen_dois:
                is_duplicate = True
                dedup_id = self.state.doi_to_slug.get(doi_clean, dedup_id)
        return is_duplicate, dedup_id

    def process(self, paper: Dict[str, Any], anchor_cat: str, tech_cat: str, anchor_list: List[str], tech_list: List[str]):
        """Deduplicates, scores, filters, and merges metadata for mined papers (thread-safe)."""
        source = paper.get('Source', 'Unknown')
        
        with self.lock:
            self.state.stats["identified"][source] = self.state.stats["identified"].get(source, 0) + 1
            
        title = paper.get('Title', '').strip()
        if not title:
            return
            
        doi_clean = Paper.normalize_doi(paper.get('DOI') or "")
        is_duplicate, dedup_id = self._check_duplicate(title, doi_clean)
        
        if is_duplicate:
            with self.lock:
                self.state.stats["duplicates_removed"] += 1
                
            if dedup_id in self.state.consolidated_results:
                existing = self.state.consolidated_results[dedup_id]
                self.resolver.resolve_existing_duplicate(existing, paper, anchor_cat, tech_cat, source)
            else:
                self.resolver.resolve_excluded_duplicate(paper, dedup_id, title, doi_clean, tech_cat, tech_list, source)
            return

        with self.lock:
            self.state.seen_ids.add(dedup_id)
            if doi_clean:
                self.state.seen_dois.add(doi_clean)
                self.state.doi_to_slug[doi_clean] = dedup_id
                
        self.resolver.register_new_paper(paper, dedup_id, title, doi_clean, tech_cat, tech_list, source)
