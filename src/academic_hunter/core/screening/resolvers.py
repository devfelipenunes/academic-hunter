import threading
from typing import Any, Dict, List

from ..infra import HunterConfig, SearchState
from ..models import Paper
from ..nlp import AcademicScorer
from .ablation import semantic_scoring_enabled
from .validators import PaperValidator

EXCLUSION_COUNTERS = {"year": "excluded_year", "anchor": "excluded_anchors"}


class PaperResolver:
    """Validates, deduplicates and registers papers, updating PRISMA stats.

    Diagnostic keys (``_hybrid_score``, ``_kw_score``, ``_sem_score``) must be
    assigned after construction: ``Paper.__init__`` populates only the fields
    declared in FIELD_SCHEMA and silently drops the rest. That is also what
    made RecomputeRanksStep's recomputation fallback load-bearing rather than
    defensive. ``Relevance_Score`` is intentionally never written here —
    RecomputeRanksStep is its only writer, and it overwrites the key with the
    rank-normalised score across the finished collection.
    """

    def __init__(self, state: SearchState, scorer: AcademicScorer, config: HunterConfig, connectors: Dict[str, Any], lock: threading.RLock, semantic_screener=None):
        self.state = state
        self.scorer = scorer
        self.config = config
        self.connectors = connectors
        self.lock = lock
        self.semantic_screener = semantic_screener
        self.validator = PaperValidator(config, scorer, semantic_screener)
        
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

    def resolve_existing_duplicate(self, existing: Any, paper: Dict[str, Any], anchor_cat: str, tech_cat: str, source: str, tech_list: List[str] = None) -> None:
        """Merges metadata and updates score/stats for an existing duplicate in results (thread-safe).

        The abstract choice and the embedding happen *before* the lock. The
        screener call is the most expensive step in the ingest, and this lock is
        the global one shared by every connector thread — holding it across a
        model call serialised the whole run.

        Three rules met here and disagreed about the abstract, and the paper
        could hold the worst of them. The choice below decided which text the
        semantic probe was computed on; ``Paper.merge`` then overwrote it with
        the longest; and the score stored beside it was the first copy's, kept
        because it already existed. One copy of the pair could therefore carry
        the abstract of the other, with a ``_sem_score`` probed on the third.

        The rule is now single and stated once: **the abstract that scores
        higher, length only as a tie-break**, applied after the merge and before
        anything is measured on it. Nobody merges a duplicate to keep the copy
        that mentions fewer domain terms -- and that tally is now the inclusion
        predicate, so choosing it by length alone decides inclusion by how
        verbose a publisher is.

        Everything measured on the abstract -- ``_sem_score``, ``_hybrid_score``,
        ``_kw_score`` -- is computed on the resolved one. ``_kw_score`` is
        recomputed on every merge rather than only when absent; a stale value
        describes text the paper no longer has, and now excludes papers that
        qualify.

        The incoming copy's matched terms are filled in here, before the merge,
        the same way ``Peer_Reviewed`` is: this path never ran the validator, so
        the match the copy earned was dropped, and ``Anchor_Terms`` could only
        ever hold the terms of the copy that arrived first while
        ``Anchor_Category`` accumulated every group the work was found under.
        """
        old_abs = existing.get('Abstract', '')
        new_abs = paper.get('Abstract', '')
        chosen_abs = old_abs
        if new_abs and new_abs != old_abs:
            title = existing.get('Title', '')
            citations = existing.get('Citations', 0)
            old_rank = self.scorer.calculate_score(title, old_abs, citations)
            new_rank = self.scorer.calculate_score(title, new_abs, citations)
            if new_rank > old_rank or (new_rank == old_rank and len(new_abs) > len(old_abs)):
                chosen_abs = new_abs

        sem_score = None
        if semantic_scoring_enabled(self.config.settings, self.semantic_screener):
            probe = {**dict(existing), "Abstract": chosen_abs}
            sem_score = round(
                self.semantic_screener.evaluate(probe, self.config.screener_config()), 4)

        with self.lock:
            min_score = self.config.min_inclusion_score()
            old_score = existing.get("_kw_score", 0.0)

            if "Peer_Reviewed" not in paper:
                paper["Peer_Reviewed"] = self.detect_peer_review(paper)
            if "Anchor_Terms" not in paper:
                _, paper["Anchor_Terms"] = self.validator.match_anchor(paper)
            if "Tech_Terms" not in paper and tech_list:
                paper["Tech_Terms"] = self.validator.match_tech_terms(paper, tech_list)

            if not isinstance(existing, Paper):
                p = Paper(existing)
                p.merge(paper, anchor_cat, tech_cat)
                existing.update(p)
            else:
                existing.merge(paper, anchor_cat, tech_cat)

            if existing.get('Abstract', '') != chosen_abs:
                existing['Abstract'] = chosen_abs

            if sem_score is not None:
                existing["_sem_score"] = sem_score

            existing["_hybrid_score"] = self.validator.compute_hybrid_score(existing)
            new_score = self.scorer.calculate_score(
                existing.get("Title", ""), existing.get("Abstract", ""),
                existing.get("Citations", 0),
            )
            existing["_kw_score"] = new_score

            if old_score < min_score and new_score >= min_score:
                self.state.stats["included_final"] += 1
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
            with self.lock:
                self.state.pending_promotions.discard(dedup_id)
            return

        min_score = self.config.min_inclusion_score()
        paper_metadata = Paper({
            "Title": title,
            "Authors": paper.get('Authors', ''),
            "Abstract": paper.get('Abstract', ''),
            "Year": paper.get("Year"),
            "URL": paper.get('URL', ''),
            "Source": source,
            "Citations": paper.get('Citations', 0),
            "Citations_Source": paper.get('Citations_Source', ''),
            "DOI": doi_clean,
            "Peer_Reviewed": paper.get("Peer_Reviewed") or self.detect_peer_review(paper),
            "Venue": paper.get('Venue', 'Unknown Venue'),
            "Anchor_Category": anchor_cat,
            "Anchor_Terms": anchor_terms,
            "Tech_Category": tech_cat,
            "Tech_Terms": tech_terms,
        })
        paper_metadata["_hybrid_score"] = relevance_score
        paper_metadata["_kw_score"] = paper.get("_kw_score", 0.0)
        paper_metadata["_sem_score"] = paper.get("_sem_score", 0.0)

        with self.lock:
            self.state.consolidated_results[dedup_id] = paper_metadata
            self.state.pending_promotions.discard(dedup_id)
            if paper_metadata["_kw_score"] >= min_score:
                self.state.stats["included_final"] += 1
                counter = EXCLUSION_COUNTERS.get(self.state.exclusion_reasons.pop(dedup_id, None))
                if counter and self.state.stats.get(counter, 0) > 0:
                    self.state.stats[counter] -= 1
            else:
                self.state.stats["excluded_technical_score"] += 1
                self.state.track_exclusion(source, "score")

    def register_new_paper(self, paper: Dict[str, Any], dedup_id: str, title: str, doi_clean: str, tech_cat: str, tech_list: List[str], source: str) -> None:
        """Registers a new unique paper, filtering and scoring it, and updating stats (thread-safe)."""
        passed, reason, anchor_cat, anchor_terms, relevance_score, tech_terms = self.validator.validate_and_score(paper, title, tech_list)
        if not passed:
            with self.lock:
                self.state.track_exclusion(source, reason)
                self.state.exclusion_reasons[dedup_id] = reason
                counter = EXCLUSION_COUNTERS.get(reason)
                if counter:
                    self.state.stats[counter] += 1
            return

        min_score = self.config.min_inclusion_score()

        kw_score = self.scorer.calculate_score(title, paper.get('Abstract', ''), paper.get('Citations', 0))
        sem_score = 0.0
        if semantic_scoring_enabled(self.config.settings, self.semantic_screener):
            sem_config = self.config.screener_config()
            sem_score = self.semantic_screener.evaluate(paper, sem_config)
            sem_score = round(sem_score, 4)

        paper_metadata = Paper({
            "Title": title,
            "Authors": paper.get('Authors', ''),
            "Abstract": paper.get('Abstract', ''),
            "Year": paper.get("Year"),
            "URL": paper.get('URL', ''),
            "Source": source,
            "Citations": paper.get('Citations', 0),
            "Citations_Source": paper.get('Citations_Source', ''),
            "DOI": doi_clean,
            "Peer_Reviewed": paper.get("Peer_Reviewed") or self.detect_peer_review(paper),
            "Venue": paper.get('Venue', 'Unknown Venue'),
            "Anchor_Category": anchor_cat,
            "Anchor_Terms": anchor_terms,
            "Tech_Category": tech_cat,
            "Tech_Terms": tech_terms,
        })
        paper_metadata["_hybrid_score"] = relevance_score
        paper_metadata["_kw_score"] = kw_score
        paper_metadata["_sem_score"] = sem_score

        with self.lock:
            self.state.consolidated_results[dedup_id] = paper_metadata
            if kw_score >= min_score:
                self.state.stats["included_final"] += 1
            else:
                self.state.stats["excluded_technical_score"] += 1
                self.state.track_exclusion(source, "score")
