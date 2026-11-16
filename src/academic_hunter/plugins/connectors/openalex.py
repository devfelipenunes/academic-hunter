import logging
from typing import Any, Dict, List

from academic_hunter import __version__

from ...core.infra.config import openalex_key
from ...core.infra.openalex import (
    OPENALEX_BASE,
    OPENALEX_DEFAULT_DELAY,
    OPENALEX_DOMAIN,
    openalex_headers,
    openalex_params,
)
from ...core.infra.transport import polite_email
from ...core.models.authors import openalex_authors
from ...core.models.utils import decode_abstract, normalize_doi
from .base import BaseConnector

logger = logging.getLogger("academic_hunter.connectors")


class OpenAlexConnector(BaseConnector):
    SOURCE_NAME = "OpenAlex"
    is_keyword_only = False
    domain = OPENALEX_DOMAIN
    default_delay = OPENALEX_DEFAULT_DELAY
    resolve_priority = 3

    @classmethod
    def unavailable_reason(cls, settings: Dict[str, Any]) -> str:
        """Cursor paging beyond OpenAlex's first page requires an API key."""
        if openalex_key(settings):
            return ""
        return (
            "no API key. OpenAlex requires a free key for cursor paging beyond the first page. "
            "Set OPENALEX_API_KEY or settings.api_keys.openalex."
        )

    def detect_peer_review(self, doc_type: str) -> str:
        cleaned_type = str(doc_type).lower()
        if any(t in cleaned_type for t in ["article", "proceedings", "journal"]):
            return "Yes"
        return "N/A"

    def get_headers(self) -> Dict[str, str]:
        return openalex_headers(self.settings, __version__)

    def resolve_metadata_by_doi(self, doi: str) -> Dict[str, Any]:
        try:
            url = f"{OPENALEX_BASE}/works/https://doi.org/{doi}"
            data = self._make_request(url, params=openalex_params(self.settings), timeout=10)
            return self.work_metadata(data)
        except Exception as e:
            logger.warning("OpenAlex metadata lookup failed for %s: %s", doi, e)
        return {}

    @staticmethod
    def work_metadata(data: Any) -> Dict[str, Any]:
        """Read what the pipeline needs out of one OpenAlex work record.

        The record is downloaded for its abstract and carries the citation count
        alongside it, so the count costs nothing extra. Absent stays absent: a
        record with no ``cited_by_count`` yields no ``Citations`` key at all,
        which is a different statement from yielding zero.
        """
        if not isinstance(data, dict):
            return {}
        metadata: Dict[str, Any] = {}
        abstract = decode_abstract(data.get('abstract_inverted_index', {}))
        if abstract:
            metadata["Abstract"] = abstract
        authors = openalex_authors(data.get('authorships'))
        if authors:
            metadata["Authors"] = authors
        citations = data.get('cited_by_count')
        if citations is not None:
            try:
                metadata["Citations"] = max(int(citations), 0)
            except (TypeError, ValueError):
                pass
        return metadata

    CITATION_CHUNK_SIZE = 50

    def fetch_citations_by_dois(
        self, dois: List[str], chunk_size: int = CITATION_CHUNK_SIZE
    ) -> Dict[str, int]:
        """Citation counts for many DOIs at once, keyed by normalised DOI.

        OpenAlex prices by request shape rather than by result count: a DOI
        singleton is free, a filtered list costs one credit and a ``search``
        costs ten. ``filter=doi:a|b|c`` is therefore the only shape that reaches
        a whole corpus — a title search per paper is ten credits each and does
        not scale. Measured: 50 DOIs in one request, 0.6 s, 1 credit.

        The keys are sorted before the filter is built because the SQLite cache
        is keyed on the serialised params: an unsorted list yields a different
        cache key on every run and never hits, so the same corpus would be paid
        for again each time.

        A chunk that fails returns nothing for its DOIs and never raises — a
        blocked or rate-limited source must leave the run to finish and the
        report to say which counts it could not obtain.
        """
        counts: Dict[str, int] = {}
        keys = sorted({normalize_doi(d) for d in dois if d})
        email = polite_email(self.settings)

        for start in range(0, len(keys), chunk_size):
            chunk = keys[start:start + chunk_size]
            params = {
                "filter": "doi:" + "|".join(chunk),
                "per_page": len(chunk),
                "select": "doi,cited_by_count",
                "mailto": email,
            }
            try:
                data = self._make_request(
                    "https://api.openalex.org/works", params=params, timeout=20
                )
                for work in (data or {}).get("results") or []:
                    doi = normalize_doi(work.get("doi") or "")
                    citation_count = work.get("cited_by_count")
                    if doi and citation_count is not None:
                        counts[doi] = max(int(citation_count), 0)
            except Exception as e:
                logger.warning(
                    "OpenAlex citation batch failed for %d DOI(s): %s", len(chunk), e
                )

        return counts

    def fetch(self, anchors: List[str], tech_strings: List[str], limit: int = 50) -> List[Dict[str, Any]]:
        email = polite_email(self.settings)
        anchor_q = ' OR '.join([f'"{a}"' for a in anchors])
        tech_q = ' OR '.join([f'"{t}"' for t in tech_strings])
        query = f"({anchor_q}) AND ({tech_q})"
        with self.lock:
            self.query_history.append({"Source": self.SOURCE_NAME, "Query": query})

        url = "https://api.openalex.org/works"
        articles = []
        cursor = "*"

        while len(articles) < limit:
            per_page = min(limit - len(articles), 200)
            params = {
                "search": query,
                "mailto": email,
                "per_page": per_page,
                "cursor": cursor,
                "filter": f"from_publication_date:{self.settings.get('start_year', 2021)}-01-01,type:article|proceedings-article"
            }

            data = self._make_request(url, params=params, timeout=20)
            if not data:
                break

            results = data.get('results') or []
            if not results:
                break

            for i in results:
                raw_doi = i.get('doi') or ""
                doi_clean = normalize_doi(raw_doi)
                abstract_text = decode_abstract(i.get('abstract_inverted_index') or {})

                primary_loc = i.get('primary_location') or {}
                source_info = primary_loc.get('source') or {}
                venue_name = source_info.get('display_name') or "Unknown Venue"

                doc_type = i.get('type') or "article"
                articles.append({
                    "Title": i.get('display_name') or "Unknown Title",
                    "Authors": openalex_authors(i.get('authorships')),
                    "Abstract": abstract_text,
                    "Year": i.get('publication_year') or "N/A",
                    "URL": i.get('doi') or i.get('id') or "",
                    "Source": self.SOURCE_NAME,
                    "Citations": i.get('cited_by_count') or 0,
                    "Citations_Source": "openalex" if i.get('cited_by_count') is not None else "",
                    "DOI": doi_clean,
                    "Type": doc_type,
                    "Peer_Reviewed": self.detect_peer_review(doc_type),
                    "Venue": venue_name
                })

            next_cursor = (data.get('meta') or {}).get('next_cursor')
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor

        return articles[:limit]
