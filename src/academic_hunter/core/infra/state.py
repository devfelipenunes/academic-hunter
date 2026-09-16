from typing import List


class SearchState:
    """Manages active search statistics, deduplication sets, and consolidated output tables."""
    def __init__(self):
        self.stats = {
            "identified": {},
            "duplicates_removed": 0,
            "excluded_year": 0,
            "excluded_anchors": 0,
            "excluded_technical_score": 0,
            "included_final": 0,
            "reranked": 0,
            #: Status -> count for the full-text step, which is opt-in and may
            #: not have run at all. Filled by `IngestFullTextStep`.
            "full_text": {},
            "exclusions_by_source": {}
        }
        self.consolidated_results = {}  # Key: Title-Slug or DOI
        self.seen_ids = set()           # Track ALL unique papers seen in this run
        self.seen_dois = set()
        self.doi_to_slug = {}
        self.query_history = []
        self.last_request_time = 0
        self.last_request_by_domain = {}
        #: Slugs a thread has claimed the right to promote from "excluded" to
        #: "included". Without the claim two threads resolving the same duplicate
        #: both pass validation and both write it, counting the stats twice.
        self.pending_promotions = set()
        #: dedup_id -> why it was rejected, so a later version that passes can
        #: undo that exact exclusion. Without it the promotion path guessed,
        #: and decremented counters belonging to other papers.
        self.exclusion_reasons = {}

    def reset(self, connectors_keys: List[str]):
        self.stats = {
            "identified": {src: 0 for src in connectors_keys},
            "duplicates_removed": 0,
            "excluded_year": 0,
            "excluded_anchors": 0,
            "excluded_technical_score": 0,
            "included_final": 0,
            "reranked": 0,
            "full_text": {},
            "exclusions_by_source": {}
        }
        self.consolidated_results = {}
        self.seen_ids = set()
        self.seen_dois = set()
        self.doi_to_slug = {}
        self.raw_scores = {}
        # Cleared, not rebound: the connectors are constructed once with these
        # very objects as arguments, so assigning a fresh list would leave them
        # appending to the old one. That silently emptied the PRISMA "Search
        # Queries History" section of every run, and never reset the pacing.
        self.query_history.clear()
        self.last_request_time = 0
        self.last_request_by_domain.clear()
        self.pending_promotions.clear()
        self.exclusion_reasons.clear()

    def track_exclusion(self, source: str, reason: str):
        """State mutation to track reasons for excluding papers by source."""
        if "exclusions_by_source" not in self.stats:
            self.stats["exclusions_by_source"] = {}
        if source not in self.stats["exclusions_by_source"]:
            self.stats["exclusions_by_source"][source] = {"year": 0, "anchor": 0, "score": 0}
        if reason in self.stats["exclusions_by_source"][source]:
            self.stats["exclusions_by_source"][source][reason] += 1
