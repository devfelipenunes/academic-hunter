from typing import Dict, Set, List, Any

class SearchState:
    """Manages active search statistics, deduplication sets, and consolidated output tables."""
    def __init__(self, connectors_keys: List[str] = None):
        self.stats = {
            "identified": {},
            "duplicates_removed": 0,
            "excluded_score": 0,
            "excluded_year": 0,
            "excluded_anchors": 0,
            "excluded_technical_score": 0,
            "included_final": 0,
            "exclusions_by_source": {}
        }
        self.consolidated_results = {}  # Key: Title-Slug or DOI
        self.seen_ids = set()           # Track ALL unique papers seen in this run
        self.seen_dois = set()
        self.doi_to_slug = {}
        self.query_history = []
        self.last_request_time = 0
        self.last_request_by_domain = {}

    def reset(self, connectors_keys: List[str]):
        self.stats = {
            "identified": {src: 0 for src in connectors_keys},
            "duplicates_removed": 0,
            "excluded_score": 0,
            "excluded_year": 0,
            "excluded_anchors": 0,
            "excluded_technical_score": 0,
            "included_final": 0,
            "exclusions_by_source": {}
        }
        self.consolidated_results = {}
        self.seen_ids = set()
        self.seen_dois = set()
        self.doi_to_slug = {}
        self.query_history = []
        self.last_request_time = 0
        self.last_request_by_domain = {}

    def track_exclusion(self, source: str, reason: str):
        """State mutation to track reasons for excluding papers by source."""
        if "exclusions_by_source" not in self.stats:
            self.stats["exclusions_by_source"] = {}
        if source not in self.stats["exclusions_by_source"]:
            self.stats["exclusions_by_source"][source] = {"year": 0, "anchor": 0, "score": 0}
        if reason in self.stats["exclusions_by_source"][source]:
            self.stats["exclusions_by_source"][source][reason] += 1
