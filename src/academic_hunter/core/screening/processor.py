import logging
import threading
import time
from typing import Any, Dict, List

from ..infra import HunterConfig, SearchState
from ..models import Paper
from ..models.utils import strip_abstract_placeholder, strip_title_label
from ..nlp import AcademicScorer
from .resolvers import PaperResolver

logger = logging.getLogger("academic_hunter")

REGISTRATION_TIMEOUT = 120.0


class PaperProcessor:
    """Handles duplicate checking, temporal filtering, anchor matching, scoring, and metadata merging for mined papers."""
    def __init__(self, state: SearchState, scorer: AcademicScorer, config: HunterConfig, connectors: Dict[str, Any], lock: threading.RLock, semantic_screener=None):
        self.state = state
        self.scorer = scorer
        self.config = config
        self.connectors = connectors
        self.lock = lock
        self.semantic_screener = semantic_screener
        self.settled = threading.Condition(lock)
        self.resolver = PaperResolver(state, scorer, config, connectors, lock, semantic_screener)

    def _settle(self, dedup_id: str) -> None:
        """Announce that the copy claiming ``dedup_id`` has finished with it."""
        with self.settled:
            self.state.pending_registrations.discard(dedup_id)
            self.settled.notify_all()

    def _await_registration(self, dedup_id: str) -> Any:
        """The entry the copy that claimed ``dedup_id`` is about to publish, or None.

        Two databases are mined at once, so two records of one study are
        routinely in flight together. The id is claimed before the copy holding
        it has finished scoring itself -- the embedding is computed outside the
        lock deliberately, so that a model call does not serialise every
        connector thread -- and a copy arriving inside that window found the id
        taken, nothing under it, and no exclusion recorded. It was dropped as if
        it were a third record of a promotion somebody else was already
        handling, on a ``debug`` line, and its metadata never reached the paper.

        That is not a duplicate being discarded, it is a paper being discarded,
        and it was measured: with two sources returning one study between them,
        half the runs lost the copy whose abstract matched the technical terms
        -- and the surviving abstract's term count is what decides inclusion.

        The wait is bounded so that a copy whose claim is never settled -- a
        crash between the two -- cannot block a worker thread for the rest of
        the run.
        """
        deadline = time.monotonic() + REGISTRATION_TIMEOUT
        with self.settled:
            while dedup_id in self.state.pending_registrations:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    logger.warning(
                        "Waited %ss for the copy of %r that claimed it and gave up; "
                        "this record is not merged into anything.",
                        REGISTRATION_TIMEOUT, dedup_id,
                    )
                    return None
                self.settled.wait(remaining)
            return self.state.consolidated_results.get(dedup_id)

    def _claim_promotion(self, dedup_id: str) -> bool:
        """Whether this call takes responsibility for re-screening ``dedup_id``.

        Atomic on purpose: two copies of a paper that was screened out can
        arrive together, and both would otherwise re-screen it and write the
        result twice.
        """
        with self.lock:
            if dedup_id in self.state.exclusion_reasons and dedup_id not in self.state.pending_promotions:
                self.state.pending_promotions.add(dedup_id)
                return True
        return False

    def process(self, paper: Dict[str, Any], anchor_cat: str, tech_cat: str, anchor_list: List[str], tech_list: List[str]):
        """Deduplicates, scores, filters, and merges metadata for mined papers (thread-safe)."""
        source = paper.get('Source', 'Unknown')

        with self.lock:
            self.state.stats["identified"][source] = self.state.stats["identified"].get(source, 0) + 1

        paper["Title"] = strip_title_label(paper.get("Title"))
        paper["Abstract"] = strip_abstract_placeholder(paper.get("Abstract"))
        title = paper["Title"]
        if not title:
            return

        doi_clean = Paper.normalize_doi(paper.get('DOI') or "")

        with self.lock:
            dedup_id = self.scorer.generate_slug(title)
            is_duplicate = dedup_id in self.state.seen_ids
            if not is_duplicate and doi_clean and doi_clean in self.state.seen_dois:
                is_duplicate = True
                dedup_id = self.state.doi_to_slug.get(doi_clean, dedup_id)

            if is_duplicate:
                self.state.stats["duplicates_removed"] += 1
                existing = self.state.consolidated_results.get(dedup_id)
            else:
                self.state.seen_ids.add(dedup_id)
                self.state.pending_registrations.add(dedup_id)
                existing = None
                if doi_clean:
                    self.state.seen_dois.add(doi_clean)
                    self.state.doi_to_slug[doi_clean] = dedup_id

        if is_duplicate:
            if existing is None and dedup_id in self.state.pending_registrations:
                existing = self._await_registration(dedup_id)

            if existing is not None:
                self.resolver.resolve_existing_duplicate(existing, paper, anchor_cat, tech_cat, source, tech_list)
            elif self._claim_promotion(dedup_id):
                self.resolver.resolve_excluded_duplicate(paper, dedup_id, title, doi_clean, tech_cat, tech_list, source)
            else:
                logger.debug(
                    "Dropped %r from %s: the same work was seen before, is not in "
                    "the collection, and another copy already holds its promotion "
                    "claim. Its metadata is not merged into the copy that won.",
                    dedup_id, source,
                )
            return

        try:
            self.resolver.register_new_paper(paper, dedup_id, title, doi_clean, tech_cat, tech_list, source)
        finally:
            self._settle(dedup_id)
