import logging
import threading
import time

from ..ports.exporter import run_dir_for
from ..screening.ablation import semantic_scoring_enabled
from .steps import (
    AutoExportObsidianStep,
    IndexResultsStep,
    IngestFullTextStep,
    RecomputeRanksStep,
    ResolveDoiStep,
    inclusion_predicate,
)

logger = logging.getLogger("academic_hunter")


class SearchPipeline:
    """Manages concurrent worker execution, pacing delays, abstract enrichment, and document export pipeline."""
    def __init__(self, hunter):
        self.hunter = hunter
        self._vector_store = None
        self._semantic_degraded = False

    @property
    def vector_store(self):
        """Lazy-init the vector store for RAG.

        The concrete store comes from ``hunter.vector_store_factory``, which the
        composition root supplies. This module used to import ``ChromaVectorStore``
        directly, coupling the domain to one adapter.
        """
        if self._vector_store is None:
            factory = getattr(self.hunter, "vector_store_factory", None)
            if factory is None:
                logger.info("No vector store factory configured, skipping RAG indexing.")
                return None
            try:
                db_dir = self.hunter.output_dir.parent / ".academic_hunter" / "chroma_db"
                self._vector_store = factory(db_dir)
            except Exception as e:
                logger.warning(f"Could not initialize vector store: {e}")
                self._vector_store = None
        return self._vector_store

    def _index_results(self):
        """Accumulate consolidated results into ChromaDB for semantic search.

        Delegates to IndexResultsStep for implementation.
        """
        IndexResultsStep(self.hunter).run()

    def _resolve_dois(self):
        """Store the DOI a paper's URL already carries, where the column is empty.

        Delegates to ResolveDoiStep. It runs after every copy of a work has been
        merged and before anything derives a paper's identity from its DOI —
        which is why it sits between the enrichment and the rank recomputation
        rather than at either end.
        """
        ResolveDoiStep(self.hunter).run()

    def _resolve_published_versions(self):
        """Ask for the published version of each preprint, and record the answer.

        After the DOI pass, so the paper's own DOI is in place before a candidate
        is compared against it, and before the rank recomputation, so the venue
        and year the report prints are the published ones. It makes network
        requests — one bibliographic query per preprint — which is why it is the
        only enrichment the run performs after the search threads have joined.
        """
        self.hunter.resolve_published_versions()

    def _included_only(self) -> dict:
        """The papers the inclusion predicate admits, keyed as before.

        One predicate, applied here and counted in the rank step, so the papers
        that survive and the number the report prints are the same set. Two
        copies of the comparison is how they drifted apart before: the report
        announced a cut that a different rule had made.

        What the predicate is, and why it is not ``Relevance_Score``, is in
        :data:`~academic_hunter.core.pipeline.steps.INCLUSION_KEY`.
        """
        key, min_score = inclusion_predicate(self.hunter)
        kept = {}
        for slug, paper in self.hunter.consolidated_results.items():
            try:
                value = float(paper.get(key) or 0.0)
            except (TypeError, ValueError):
                value = 0.0
            if value >= min_score:
                kept[slug] = paper
        return kept

    def _recompute_ranks(self, timestamp: str = ""):
        """Re-rank all papers using multiplicative rank normalization.

        Delegates to RecomputeRanksStep for implementation. The timestamp is
        what the step writes the score distribution under, so the run keeps the
        signals of the papers the threshold is about to remove.
        """
        RecomputeRanksStep(self.hunter, timestamp).run()

    def _ingest_full_text(self):
        """Fetch and index full text for the qualified papers.

        Opt-in (`settings.fulltext.enabled`) and a no-op when it is off, which
        is the default. Delegates to IngestFullTextStep.
        """
        IngestFullTextStep(self.hunter).run()

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
                except Exception as e:
                    logger.error(f"[{source_name} Worker] {e}")
                    results = None

                for paper in results or []:
                    try:
                        consolidated_cat = self.hunter.config.keyword_only_category
                        self.hunter._process_paper(paper, anchor_cat, consolidated_cat, anchor_list, tech_list)
                    except Exception as e:
                        logger.error(f"[{source_name} Worker] dropped one paper: {e}")

                time.sleep(1.0)
            else:
                for tech_cat, tech_list in self.hunter.tech_strings.items():
                    try:
                        results = fetch_fn(anchor_list, tech_list, limit=limit_per_source)
                    except Exception as e:
                        logger.error(f"[{source_name} Worker] {e}")
                        results = None

                    for paper in results or []:
                        try:
                            self.hunter._process_paper(paper, anchor_cat, tech_cat, anchor_list, tech_list)
                        except Exception as e:
                            logger.error(f"[{source_name} Worker] dropped one paper: {e}")

                    time.sleep(1.0)

    def _reset_run_state(self) -> None:
        """Start a run from a clean slate.

        ``blocked_sources`` lives on the config, which outlives the run: without
        clearing it here, one 429 silences a source for every later run in the
        same process. The block belongs to the run, not to the session.

        ``pacing_delays`` outlives the run the same way and for the same reason
        — the connector is built once and reused — and it is escalated, never
        lowered. Every 429 doubles it, so a server that stays up across runs
        doubles its own delays each time it is throttled: after four throttled
        runs a 3-second source is pacing at 48 seconds, and nothing reports why
        the run got slow. The rate limit it was backing off from is long over.

        Clearing alone went one step too far. ``setup_pacing`` writes the delay
        a credential buys into the same dict — Semantic Scholar drops from 4 s to
        1 s when a key is configured — and that write happens once, at
        construction. So the first run's reset wiped the key's discount as well
        as the escalation, and every source fell back to its unkeyed default for
        the rest of the process. The hook is re-run here, which restores the dict
        to the state it was built in: the escalation is gone, the credential's
        effect is not.
        """
        self.hunter.state.reset(list(self.hunter.connectors.keys()))
        self.hunter.blocked_sources.clear()
        for connector in self.hunter.connectors.values():
            delays = getattr(connector, "pacing_delays", None)
            if delays is not None:
                delays.clear()
            setup = getattr(connector, "setup_pacing", None)
            if setup is not None:
                setup()

    def _warm_semantic_screener(self) -> None:
        """Load the embedding model here, before a worker thread can race it.

        `SemanticScreener.warm` has the measurements. The model is only needed
        when the ablation mode scores semantically, and a keyword-only run
        should not pay 79 MB for something it will not call.

        A refusal is recorded rather than discarded. `warm` is the one place
        that knows a load was attempted and how it went, and the run it is
        reporting on is over by the time anything reads the flag back.
        """
        screener = getattr(self.hunter, "semantic_screener", None)
        if screener is None:
            return
        if not semantic_scoring_enabled(self.hunter.settings, screener):
            return
        if not screener.warm():
            self._semantic_degraded = True

    def _unavailable_sources(self) -> dict:
        """Connectors that cannot run with the current settings, and why.

        Asked here rather than at construction: a credential can be configured
        between this run and the next, and `run_search` builds a fresh hunter
        that re-reads the config file. The connectors stay registered and
        instantiated either way -- the facades reach into `hunter.connectors` by
        name -- so this only decides who gets a thread.

        The answer is written to ``stats`` so the run's artifact can carry it.
        A source that was never queried and a source that was queried and found
        nothing both reached the report as ``0``, and nothing on disk told them
        apart. ``blocked_sources`` is recorded next to it, after the threads
        join: a source is only blocked by a 429 it meets *during* the run.
        """
        reasons = {}
        for name, connector in self.hunter.connectors.items():
            reason = type(connector).unavailable_reason(self.hunter.settings)
            if reason:
                reasons[name] = reason
        if reasons:
            logger.warning(
                "⏭️ Not querying %s: %s",
                ", ".join(reasons),
                " ".join(reasons.values()),
            )
        return reasons

    def run(self, limit_per_source: int = 100):
        logger.info("🚀 Initializing Multi-Threaded Academic Hunter V2 Pipeline...")
        timestamp = time.strftime("%Y%m%d_%H%M%S")

        self._reset_run_state()
        self.hunter.last_request_time = time.time()
        self._warm_semantic_screener()

        unavailable = self._unavailable_sources()
        self.hunter.state.stats["unavailable_sources"] = unavailable

        threads = []
        for src, conn in self.hunter.connectors.items():
            if src in unavailable:
                continue
            domain = getattr(conn, "domain", "")
            if domain in self.hunter.blocked_sources:
                continue
            t = threading.Thread(target=self._api_worker, args=(src, None, limit_per_source))
            t.daemon = True
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        self.hunter.state.stats["blocked_sources"] = sorted(self.hunter.blocked_sources)

        elapsed = round(time.time() - self.hunter.last_request_time, 2)
        logger.info(f"⏱️ Mining completed in {elapsed} seconds.")

        self.hunter.enrich_metadata()
        self._resolve_dois()
        self._resolve_published_versions()

        self._recompute_ranks(timestamp)

        final_qualifiers = self._included_only()

        self.hunter.consolidated_results = final_qualifiers

        self._ingest_full_text()

        self.hunter.export_results(timestamp)
        self.hunter.generate_prisma_report(timestamp)

        self._index_results()
        self._auto_export_to_obsidian(timestamp)

        screener = getattr(self.hunter, "semantic_screener", None)
        degraded = self._semantic_degraded or getattr(screener, "degraded", False)
        if screener is not None and degraded:
            logger.warning(
                "⚠️ Semantic screener ran in ZERO-VECTOR mode: every semantic "
                "score is 0.0. Treat this run's scores as keyword-only."
            )

        logger.info("💎 PIPELINE FINISHED!")
        logger.info("📊 PRISMA STATS:")
        logger.info(f"   - Identified: {self.hunter.stats['identified']}")
        logger.info(f"   - Duplicates Removed: {self.hunter.stats['duplicates_removed']}")
        logger.info(f"   - Excluded (Publication Year): {self.hunter.stats['excluded_year']}")
        logger.info(f"   - Excluded (No Industry Anchors): {self.hunter.stats['excluded_anchors']}")
        logger.info(f"   - Excluded (Below the Inclusion Predicate): {self.hunter.stats['excluded_technical_score']}")
        logger.info(f"   - Inclusion Predicate: {self.hunter.stats.get('inclusion_predicate')}")
        logger.info(f"   - Final Included: {self.hunter.stats['included_final']}")
        if "reranked" in self.hunter.stats:
            logger.info(
                f"   - Reranked (cross-encoder): {self.hunter.stats['reranked']}"
            )

        report = run_dir_for(timestamp, self.hunter.output_dir) / f"RELATORIO_ELITE_{timestamp}.md"
        return str(report)

    def _auto_export_to_obsidian(self, timestamp: str):
        """Auto-export elite report to Obsidian vault if configured."""
        AutoExportObsidianStep(self.hunter, timestamp=timestamp).run()
