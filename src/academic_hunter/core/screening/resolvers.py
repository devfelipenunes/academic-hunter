import threading
from typing import Dict, Any, List
from ..models import Paper
from ..infra import SearchState, HunterConfig
from ..nlp import AcademicScorer
from .validators import PaperValidator

class PaperResolver:
    def __init__(self, state: SearchState, scorer: AcademicScorer, config: HunterConfig, connectors: Dict[str, Any], lock: threading.RLock):
        self.state = state
        self.scorer = scorer
        self.config = config
        self.connectors = connectors
        self.lock = lock
        self.validator = PaperValidator(config, scorer)
        
        # Precompute normalized connector names for O(1) lookup
        self._norm_connectors = {self._norm(name): conn for name, conn in connectors.items()}

    @staticmethod
    def _norm(name: str) -> str:
        return name.lower().replace(" ", "").replace("_", "").replace("-", "")

    def detect_peer_review(self, paper: Dict[str, Any]) -> str:
        """Determines if a document is peer reviewed based on its type/venue."""
        source_name = paper.get("Source")
        if not source_name:
            return "N/A"
            
        norm_source = self._norm(source_name)
        connector = self._norm_connectors.get(norm_source)
        if connector:
            return connector.detect_peer_review(paper.get("Type", ""))
        return "N/A"

    def resolve_existing_duplicate(self, existing: Any, paper: Dict[str, Any], anchor_cat: str, tech_cat: str, source: str) -> None:
        """Merges metadata and updates score/stats for an existing duplicate in results (thread-safe)."""
        with self.lock:
            min_score = self.config.settings.get('min_relevance_score', 5.0)
            old_score = existing.get("Relevance_Score", 0.0)
            
            # Prefer the abstract that has a higher length or yields a better relevance score
            old_abs = existing.get('Abstract', '')
            new_abs = paper.get('Abstract', '')
            if new_abs and new_abs != old_abs:
                old_abs_score = self.scorer.calculate_score(existing.get('Title', ''), old_abs, existing.get('Citations', 0))
                new_abs_score = self.scorer.calculate_score(existing.get('Title', ''), new_abs, existing.get('Citations', 0))
                if new_abs_score > old_abs_score or len(new_abs) > len(old_abs):
                    existing['Abstract'] = new_abs

            # Ensure Peer_Reviewed is populated in the new paper dictionary if missing
            if "Peer_Reviewed" not in paper:
                paper["Peer_Reviewed"] = self.detect_peer_review(paper)

            # Merge metadata
            if not isinstance(existing, Paper):
                p = Paper(existing)
                p.merge(paper, anchor_cat, tech_cat)
                existing.update(p)
            else:
                existing.merge(paper, anchor_cat, tech_cat)
            
            # Recalculate score after merging metadata
            new_score = self.scorer.calculate_score(existing.get("Title", ""), existing.get("Abstract", ""), existing.get("Citations", 0))
            existing["Relevance_Score"] = new_score
            
            # Correct the stats if the paper is now promoted
            if old_score < min_score and new_score >= min_score:
                self.state.stats["included_final"] += 1
                if self.state.stats["excluded_score"] > 0:
                    self.state.stats["excluded_score"] -= 1
                if self.state.stats["excluded_technical_score"] > 0:
                    self.state.stats["excluded_technical_score"] -= 1
                
                source_orig = existing.get('Source', source).split(', ')[0]
                if "exclusions_by_source" in self.state.stats and source_orig in self.state.stats["exclusions_by_source"]:
                    if self.state.stats["exclusions_by_source"][source_orig]["score"] > 0:
                        self.state.stats["exclusions_by_source"][source_orig]["score"] -= 1

    def resolve_excluded_duplicate(self, paper: Dict[str, Any], dedup_id: str, title: str, doi_clean: str, tech_cat: str, tech_list: List[str], source: str) -> None:
        """Processes a duplicate that was previously excluded (passes filters and updates stats)."""
        passed, reason, anchor_cat, anchor_terms, relevance_score, tech_terms = self.validator.validate_and_score(paper, title, tech_list)
        if not passed:
            return

        min_score = self.config.settings.get('min_relevance_score', 5.0)
        paper_metadata = Paper({
            "Title": title,
            "Abstract": paper.get('Abstract', ''),
            "Year": paper.get("Year"),
            "URL": paper.get('URL', ''),
            "Source": source,
            "Citations": paper.get('Citations', 0),
            "DOI": doi_clean,
            "Peer_Reviewed": paper.get("Peer_Reviewed") or self.detect_peer_review(paper),
            "Venue": paper.get('Venue', 'Unknown Venue'),
            "Anchor_Category": anchor_cat,
            "Anchor_Terms": anchor_terms,
            "Tech_Category": tech_cat,
            "Tech_Terms": tech_terms,
            "Relevance_Score": relevance_score
        })
        
        with self.lock:
            self.state.consolidated_results[dedup_id] = paper_metadata
            if relevance_score >= min_score:
                self.state.stats["included_final"] += 1
                if self.state.stats.get("excluded_anchors", 0) > 0:
                    self.state.stats["excluded_anchors"] -= 1
                elif self.state.stats.get("excluded_year", 0) > 0:
                    self.state.stats["excluded_year"] -= 1
                elif self.state.stats.get("excluded_score", 0) > 0:
                    self.state.stats["excluded_score"] -= 1
            else:
                self.state.stats["excluded_technical_score"] += 1
                self.state.stats["excluded_score"] += 1
                self.state.track_exclusion(source, "score")

    def register_new_paper(self, paper: Dict[str, Any], dedup_id: str, title: str, doi_clean: str, tech_cat: str, tech_list: List[str], source: str) -> None:
        """Registers a new unique paper, filtering and scoring it, and updating stats (thread-safe)."""
        passed, reason, anchor_cat, anchor_terms, relevance_score, tech_terms = self.validator.validate_and_score(paper, title, tech_list)
        if not passed:
            self.state.track_exclusion(source, reason)
            with self.lock:
                if reason == "year":
                    self.state.stats["excluded_year"] += 1
                elif reason == "anchor":
                    self.state.stats["excluded_anchors"] += 1
            return

        min_score = self.config.settings.get('min_relevance_score', 5.0)
        paper_metadata = Paper({
            "Title": title,
            "Abstract": paper.get('Abstract', ''),
            "Year": paper.get("Year"),
            "URL": paper.get('URL', ''),
            "Source": source,
            "Citations": paper.get('Citations', 0),
            "DOI": doi_clean,
            "Peer_Reviewed": paper.get("Peer_Reviewed") or self.detect_peer_review(paper),
            "Venue": paper.get('Venue', 'Unknown Venue'),
            "Anchor_Category": anchor_cat,
            "Anchor_Terms": anchor_terms,
            "Tech_Category": tech_cat,
            "Tech_Terms": tech_terms,
            "Relevance_Score": relevance_score
        })

        with self.lock:
            self.state.consolidated_results[dedup_id] = paper_metadata
            if relevance_score >= min_score:
                self.state.stats["included_final"] += 1
            else:
                self.state.stats["excluded_technical_score"] += 1
                self.state.stats["excluded_score"] += 1
                self.state.track_exclusion(source, "score")
