import logging
import math
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Tuple

from ..infra import SearchState
from ..models import Paper
from ..models.published_version import (
    PREPRINT,
    PREPRINT_LIKELY,
    best_match,
    is_preprint,
)
from ..models.strategies import strategy_set_join
from ..models.utils import arxiv_doi, arxiv_id_from_url, strip_abstract_placeholder

logger = logging.getLogger("academic_hunter")

CITATION_SOURCE_NONE = "none"
CITATION_SOURCE_UNRESOLVED = "unresolved"
CITATION_SOURCE_BATCH = "openalex-batch"


class MetadataEnricher:
    """Fills in what the connectors know about a DOI: a missing abstract, and a citation count reported as zero."""

    def __init__(
        self,
        connectors: Dict[str, Any],
        state: SearchState,
        lock: threading.RLock,
        settings: Dict[str, Any] = None,
    ):
        self.connectors = connectors
        self.state = state
        self.lock = lock
        self.settings = settings or {}

    def _resolving_connectors(self) -> List[Any]:
        """The connectors that resolve a DOI, best first.

        Every connector answers ``resolve_metadata_by_doi`` through the base
        class, which returns nothing, so the capability says nothing here and
        ``resolve_priority`` is the only statement that a source is a DOI
        resolver at all: 0 means it is not, and those are dropped rather than
        asked for an empty answer.
        """
        ranked = [
            (getattr(connector, "resolve_priority", 0), connector)
            for connector in self.connectors.values()
        ]
        ranked = [pair for pair in ranked if pair[0] > 0]
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        return [connector for _, connector in ranked]

    def _ranked_connectors(self, capability: str) -> List[Any]:
        """The connectors offering ``capability``, best first.

        For a capability the base class does not provide, having it is what says
        a source may be asked at all, so ``resolve_priority`` only says how much
        its answer is preferred — a source that declares none is ranked last
        rather than dropped, because a source that can answer must not be
        skipped in silence. The name breaks ties, so two sources claiming the
        same priority are ranked the same way on every run instead of in the
        order the connectors happened to be registered.
        """
        ranked = [
            (
                getattr(connector, "resolve_priority", 0),
                str(getattr(connector, "SOURCE_NAME", "") or connector.__class__.__name__),
                connector,
            )
            for connector in self.connectors.values()
            if callable(getattr(connector, capability, None))
        ]
        ranked.sort(key=lambda entry: (-entry[0], entry[1]))
        return [connector for _, _, connector in ranked]

    @staticmethod
    def _stamp(paper: Dict[str, Any], source: str) -> None:
        paper["Citations_Source"] = strategy_set_join(paper.get("Citations_Source", ""), source)

    def lookup_metadata_by_doi(self, doi: str) -> Tuple[Dict[str, Any], str]:
        """Everything the DOI-resolving connectors can supply, and which one supplied it.

        Connectors are asked in ``resolve_priority`` order and the first answer
        for each field wins, so a high-priority source keeps its abstract while
        a lower one can still contribute the only citation count on offer. A
        connector implementing only the narrower ``resolve_abstract_by_doi`` is
        read as answering for the abstract alone, so it keeps working unchanged.
        """
        if not doi:
            return {}, ""
        doi_clean = Paper.normalize_doi(doi)
        metadata: Dict[str, Any] = {}
        source = ""

        for connector in self._resolving_connectors():
            try:
                resolver = getattr(connector, "resolve_metadata_by_doi", None)
                if callable(resolver):
                    answer = resolver(doi_clean)
                else:
                    answer = {"Abstract": connector.resolve_abstract_by_doi(doi_clean)}
                if not isinstance(answer, dict):
                    continue
                for field, value in answer.items():
                    if value not in (None, "") and field not in metadata:
                        metadata[field] = value
                if answer and not source:
                    source = str(getattr(connector, "SOURCE_NAME", "") or connector.__class__.__name__)
            except Exception as e:
                logger.debug(f"[{connector.__class__.__name__}] Error resolving DOI {doi_clean}: {e}")

        return metadata, source

    def fetch_metadata_by_doi(self, doi: str) -> Dict[str, Any]:
        return self.lookup_metadata_by_doi(doi)[0]

    def fetch_abstract_by_doi(self, doi: str) -> str:
        return str(self.fetch_metadata_by_doi(doi).get("Abstract") or "")

    def enrich_abstracts(self):
        logger.info("🔍 Enriching missing abstracts for qualified papers...")
        with self.lock:
            to_enrich = []
            for slug, paper in self.state.consolidated_results.items():
                abstract = strip_abstract_placeholder(paper.get("Abstract"))
                if not abstract.strip() and paper.get("DOI"):
                    to_enrich.append((slug, paper))

        enriched_count = 0
        if not to_enrich:
            logger.info("✅ Abstract enrichment complete. Enriched 0 papers.")
            return

        def task(slug, paper):
            metadata, source = self.lookup_metadata_by_doi(paper.get("DOI"))
            return slug, paper, metadata, source

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(task, slug, paper) for slug, paper in to_enrich]
            for future in as_completed(futures):
                try:
                    slug, paper, metadata, source = future.result()
                    if not metadata:
                        continue
                    with self.lock:
                        abstract = strip_abstract_placeholder(metadata.get("Abstract"))
                        citation_count = metadata.get("Citations")
                        if abstract:
                            paper["Abstract"] = abstract
                            paper["_abstract_enriched"] = True
                            enriched_count += 1
                        if citation_count is not None and not int(paper.get("Citations") or 0):
                            paper["Citations"] = int(citation_count)
                        if abstract or citation_count is not None:
                            paper["_kw_score"] = None
                            paper["_sem_score"] = None
                        if source:
                            self._stamp(paper, f"{source.lower()}-doi")
                        if abstract:
                            logger.info(f"Enriched '{paper.get('Title')[:40]}...'")
                except Exception as e:
                    logger.error(f"Enrichment error: {e}")

        logger.info(f"✅ Abstract enrichment complete. Enriched {enriched_count} papers.")

    @staticmethod
    def _citation_key(paper: Dict[str, Any]) -> str:
        """The identifier to ask a source about: the DOI, else the arXiv DataCite DOI.

        arXiv mints a DataCite DOI for every preprint, and the connectors already
        carry the arXiv id inside ``URL``, so a paper with no publisher DOI is
        still addressable rather than written off.
        """
        doi = Paper.normalize_doi(paper.get("DOI") or "")
        if doi:
            return doi
        return arxiv_doi(arxiv_id_from_url(paper.get("URL") or ""))

    def backfill_citations(self) -> Dict[str, Any]:
        """Ask for the counts no connector reported, and record who answered.

        Only a zero is asked after, so a count a source already reported is never
        overwritten: the rule keeps the backfill purely additive and leaves no
        room for a maximum to hide which source disagreed with which.

        Invalidation is the load-bearing part. ``calculate_score`` already added
        ``log10(citations + 1)`` when the paper was ingested, against the zero it
        then carried, and the rank step recomputes a keyword score only when it
        is ``None``. Without nulling it, a corrected count would reach the report
        and the sidecar while the score kept the number it was built on — and
        since that score is the inclusion predicate, membership would follow the
        false zero.
        """
        config = self.settings.get("citations_backfill")
        if config is False:
            logger.info("Citation backfill disabled by configuration.")
            return {}
        config = config if isinstance(config, dict) else {}
        if config.get("enabled", True) is False:
            logger.info("Citation backfill disabled by citations_backfill.enabled.")
            return {}

        ranked = self._ranked_connectors("fetch_citations_by_dois")
        connector = ranked[0] if ranked else None
        if connector is None:
            logger.info("No connector offers batched citation counts; skipping the backfill.")
            return {}

        with self.lock:
            keys: Dict[str, List[str]] = {}
            without_key = 0
            for slug, paper in self.state.consolidated_results.items():
                if int(paper.get("Citations") or 0):
                    continue
                key = self._citation_key(paper)
                if key:
                    keys.setdefault(key, []).append(slug)
                else:
                    without_key += 1
                    self._stamp(paper, CITATION_SOURCE_NONE)

        asked = sorted(keys)
        papers_asked = sum(len(slugs) for slugs in keys.values())
        if not asked:
            summary = {
                "papers_asked": 0,
                "papers_resolved": 0,
                "papers_recovered": 0,
                "papers_unresolved": 0,
                "papers_without_identifier": without_key,
                "requests": 0,
            }
            self.state.stats["citation_backfill"] = summary
            return summary

        chunk_size = int(getattr(connector, "CITATION_CHUNK_SIZE", 50) or 50)
        try:
            counts = connector.fetch_citations_by_dois(asked)
        except Exception as e:
            logger.warning("Citation backfill failed entirely: %s", e)
            counts = {}
        if not isinstance(counts, dict):
            logger.warning("Citation backfill returned %s instead of a mapping; ignoring it.", type(counts).__name__)
            counts = {}

        invalidate = config.get("invalidate_scores", True)
        papers_resolved = papers_unresolved = papers_recovered = 0

        with self.lock:
            for key in asked:
                slugs = keys[key]
                if key not in counts:
                    papers_unresolved += len(slugs)
                    for slug in slugs:
                        paper = self.state.consolidated_results.get(slug)
                        if paper is not None:
                            self._stamp(paper, CITATION_SOURCE_UNRESOLVED)
                    continue
                papers_resolved += len(slugs)
                value = int(counts[key] or 0)
                for slug in slugs:
                    paper = self.state.consolidated_results.get(slug)
                    if paper is None:
                        continue
                    if value:
                        papers_recovered += 1
                    if value > int(paper.get("Citations") or 0):
                        paper["Citations"] = value
                        if invalidate:
                            paper["_kw_score"] = None
                            paper["_sem_score"] = None
                    self._stamp(paper, CITATION_SOURCE_BATCH)

        summary = {
            "papers_asked": papers_asked,
            "papers_resolved": papers_resolved,
            "papers_recovered": papers_recovered,
            "papers_unresolved": papers_unresolved,
            "papers_without_identifier": without_key,
            "requests": math.ceil(len(asked) / chunk_size),
        }
        self.state.stats["citation_backfill"] = summary
        logger.info(f"📈 Citation backfill: {summary}")
        return summary

    def _published_version_connector(self) -> Any:
        """The connector to ask for a published version, highest priority first.

        Ordered rather than picked by dictionary order, which is the order the
        connectors happened to be registered in and says nothing about whose
        answer to prefer. ``resolve_priority`` is the repository's existing
        statement of that preference — it is what orders the abstract and
        citation lookups — so the same ranking decides this one instead of a
        second ranking invented here.
        """
        ranked = self._ranked_connectors("find_published_version")
        return ranked[0] if ranked else None

    def resolve_published_versions(self) -> Dict[str, Any]:
        """Find the published version of each preprint, and say what was found.

        Measured on the delivered run: 109 of 310 papers are preprints, and the
        report names the preprint's own venue and year for a work that was
        published somewhere else — an arXiv posting of 2021 standing in for the
        conference paper it is the preprint of.

        What this writes is ``Venue``, ``Year`` and ``Peer_Reviewed``. The DOI is
        **not** written, and that is the load-bearing decision: ``DOI`` is not
        only a bibliographic field here, it is the identity — ``doc_id_for``
        turns it into the key that names the paper in the run's own artifacts,
        the score distribution and the full-text ``parent_id`` alike. Replacing
        an arXiv DOI with a publisher DOI after those were keyed would move the
        keys a second time, and whatever was indexed under the old ones would be
        orphaned. The published DOI is recorded beside the paper's own, in the
        sidecar and in the report.

        A paper that is not matched is left exactly as it was. A candidate that
        clears the title bar and shares no surname is refused rather than
        promoted, and one that clears both is still only ``Likely`` — a
        bibliographic search can witness that a record exists, not that anyone
        reviewed it.
        """
        config = self.settings.get("published_version")
        if config is False:
            logger.info("Published-version search disabled by configuration.")
            return {}
        config = config if isinstance(config, dict) else {}
        if config.get("enabled", True) is False:
            logger.info("Published-version search disabled by published_version.enabled.")
            return {}

        connector = self._published_version_connector()
        if connector is None:
            logger.info(
                "No connector offers a published-version lookup; every preprint "
                "keeps the venue and year it arrived with."
            )
            return {}

        with self.lock:
            targets = []
            without_identifier = 0
            for slug, paper in self.state.consolidated_results.items():
                if str(paper.get("Peer_Reviewed") or "") != PREPRINT:
                    continue
                arxiv_id = arxiv_id_from_url(paper.get("URL") or "")
                if is_preprint(paper, arxiv_id):
                    targets.append((slug, paper))
                else:
                    without_identifier += 1

        start_year = self._start_year()
        asked = failed = promoted = 0
        title_only = 0
        before_start_year = []
        promotions = []

        for slug, paper in targets:
            asked += 1
            try:
                answer = connector.find_published_version(
                    paper.get("Title") or "", paper.get("Authors") or ""
                )
            except Exception as e:
                logger.debug("Published-version lookup failed for %s: %s", slug, e)
                failed += 1
                continue
            candidate, reason = best_match(paper, (answer or {}).get("candidates"))
            if not candidate:
                continue

            published_doi = str(candidate.get("DOI") or "").strip()
            published_venue = str(candidate.get("Venue") or "").strip()
            published_year = candidate.get("Year")
            if str(published_year or "").strip() in ("", "N/A"):
                published_year = ""

            with self.lock:
                paper["Peer_Reviewed"] = PREPRINT_LIKELY
                if published_venue:
                    paper["Venue"] = published_venue
                if published_year:
                    paper["Year"] = published_year
            promoted += 1
            if reason == "title_only":
                title_only += 1
            if self._before_start_year(published_year, start_year):
                before_start_year.append(
                    {"title": paper.get("Title"), "year": published_year, "doi": published_doi}
                )
            promotions.append({
                "title": str(paper.get("Title") or ""),
                "doi": str(paper.get("DOI") or ""),
                "published_doi": published_doi,
                "venue": published_venue,
                "year": published_year,
                "match": reason,
            })

        summary = {
            "preprints": len(targets) + without_identifier,
            "asked": asked,
            "failed": failed,
            "promoted": promoted,
            "unmatched": asked - promoted - failed,
            "promoted_on_title_alone": title_only,
            "without_identifier": without_identifier,
            "before_start_year": before_start_year,
            "promotions": promotions,
        }
        self.state.stats["published_version"] = summary

        logger.info(
            "📚 Published versions: %d of %d preprint(s) promoted to 'Likely' "
            "(%d confirmed by a shared author, %d on the title alone); %d left as "
            "they were; %d preprint(s) carry no identifier to be the preprint of.",
            promoted, asked, promoted - title_only, title_only,
            summary["unmatched"], without_identifier,
        )
        if before_start_year:
            logger.warning(
                "⚠️ %d promoted paper(s) are dated before settings.start_year=%s, "
                "so the exported set now reaches further back than the run's own "
                "temporal filter: %s",
                len(before_start_year), start_year,
                ", ".join(f"{entry['title']!r} ({entry['year']})" for entry in before_start_year[:3]),
            )
        return summary

    def _start_year(self) -> Any:
        configured = self.settings.get("start_year")
        try:
            return int(configured)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _before_start_year(year: Any, start_year: Any) -> bool:
        if start_year is None or not year:
            return False
        try:
            return int(year) < start_year
        except (TypeError, ValueError):
            return False

    def enrich(self) -> Dict[str, Any]:
        """Both phases, in the order the pipeline needs them: text first, then counts.

        The search for a published version is not here. It runs after the DOI
        pass, which is a pipeline step rather than an enrichment phase, so the
        ordering between the two is visible in the pipeline that depends on it
        instead of being an invariant of this method.
        """
        self.enrich_abstracts()
        return self.backfill_citations()
