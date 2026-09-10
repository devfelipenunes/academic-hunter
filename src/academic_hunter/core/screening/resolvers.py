import threading
from typing import Dict, Any, List
from ..models import Paper
from ..infra import SearchState, HunterConfig
from ..nlp import AcademicScorer
from .validators import PaperValidator

class PaperResolver:
    def __init__(self, state: SearchState, scorer: AcademicScorer, config: HunterConfig, connectors: Dict[str, Any], lock: threading.RLock, semantic_screener=None):
        self.state = state
        self.scorer = scorer
        self.config = config
        self.connectors = connectors
        self.lock = lock
        self.semantic_screener = semantic_screener
        self.validator = PaperValidator(config, scorer, semantic_screener)
        
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
        """Merges metadata and updates score/stats for an existing duplicate in results (thread-safe).

        The abstract choice and the embedding happen *before* the lock. The
        screener call is the most expensive step in the ingest, and this lock is
        the global one shared by every connector thread — holding it across a
        model call serialised the whole run.
        """
        old_abs = existing.get('Abstract', '')
        new_abs = paper.get('Abstract', '')
        chosen_abs = old_abs
        if new_abs and new_abs != old_abs:
            # Prefer the longer abstract, or the one that scores better.
            title = existing.get('Title', '')
            citations = existing.get('Citations', 0)
            if (self.scorer.calculate_score(title, new_abs, citations)
                    > self.scorer.calculate_score(title, old_abs, citations)
                    or len(new_abs) > len(old_abs)):
                chosen_abs = new_abs

        sem_score = None
        if self.semantic_screener is not None:
            mode = self.config.settings.get('ablation', {}).get('mode', 'hybrid')
            if mode != 'keyword':
                probe = {**dict(existing), "Abstract": chosen_abs}
                sem_score = round(
                    self.semantic_screener.evaluate(probe, self.config.screener_config()), 4)

        with self.lock:
            min_score = self.config.min_inclusion_score()
            old_score = existing.get("_hybrid_score", 0.0)

            if chosen_abs != old_abs:
                existing['Abstract'] = chosen_abs

            # Ensure Peer_Reviewed is populated in the new paper dictionary if missing
            if "Peer_Reviewed" not in paper:
                paper["Peer_Reviewed"] = self.detect_peer_review(paper)

            if not isinstance(existing, Paper):
                p = Paper(existing)
                p.merge(paper, anchor_cat, tech_cat)
                existing.update(p)
            else:
                existing.merge(paper, anchor_cat, tech_cat)

            if sem_score is not None:
                existing["_sem_score"] = sem_score

            # Recalculate the inclusion score after merging metadata (respects
            # ablation mode). Written to `_hybrid_score`, never to
            # `Relevance_Score` — the latter is owned solely by
            # RecomputeRanksStep, which overwrites it with the rank-normalised
            # score across the finished collection. Writing an inclusion score
            # there put two scales behind one key.
            new_score = self.validator.compute_hybrid_score(existing)
            existing["_hybrid_score"] = new_score
            # Store raw scores for rank normalization
            if "_kw_score" not in existing:
                existing["_kw_score"] = self.scorer.calculate_score(
                    existing.get("Title", ""), existing.get("Abstract", ""), existing.get("Citations", 0))

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

        min_score = self.config.min_inclusion_score()
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
        })
        # `Paper.__init__` populates only the fields declared in FIELD_SCHEMA, so
        # diagnostic keys must be assigned after construction — passing them to
        # the constructor silently drops them. `Relevance_Score` is intentionally
        # left unset: RecomputeRanksStep is its only writer.
        paper_metadata["_hybrid_score"] = relevance_score
        paper_metadata["_kw_score"] = paper.get("_kw_score", 0.0)
        paper_metadata["_sem_score"] = paper.get("_sem_score", 0.0)
        
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
            # track_exclusion mutates `exclusions_by_source`, so it belongs
            # inside the lock with the rest of the stats it updates.
            with self.lock:
                self.state.track_exclusion(source, reason)
                if reason == "year":
                    self.state.stats["excluded_year"] += 1
                elif reason == "anchor":
                    self.state.stats["excluded_anchors"] += 1
            return

        min_score = self.config.min_inclusion_score()

        # Compute raw keyword and semantic scores for rank normalization
        kw_score = self.scorer.calculate_score(title, paper.get('Abstract', ''), paper.get('Citations', 0))
        sem_score = 0.0
        if self.semantic_screener is not None:
            sem_config = self.config.screener_config()
            sem_score = self.semantic_screener.evaluate(paper, sem_config)
            sem_score = round(sem_score, 4)  # keep precision for rank comparison

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
        })
        # `Paper.__init__` populates only the fields declared in FIELD_SCHEMA, so
        # diagnostic keys must be assigned after construction — passing them to
        # the constructor silently drops them (which is what made
        # RecomputeRanksStep's recomputation fallback load-bearing rather than
        # defensive). `Relevance_Score` is intentionally left unset:
        # RecomputeRanksStep is its only writer.
        paper_metadata["_hybrid_score"] = relevance_score
        paper_metadata["_kw_score"] = kw_score
        paper_metadata["_sem_score"] = sem_score

        with self.lock:
            self.state.consolidated_results[dedup_id] = paper_metadata
            if relevance_score >= min_score:
                self.state.stats["included_final"] += 1
            else:
                self.state.stats["excluded_technical_score"] += 1
                self.state.stats["excluded_score"] += 1
                self.state.track_exclusion(source, "score")
