import logging
from typing import Any, Dict, List

from academic_hunter.core.infra.config import semantic_scholar_key
from academic_hunter.core.models.authors import listed_authors

from .base import BaseConnector, keyword_terms

logger = logging.getLogger("academic_hunter.connectors")


class SemanticScholarConnector(BaseConnector):
    fetch_suffix = "semantic_scholar"
    SOURCE_NAME = "Semantic Scholar"
    is_keyword_only = True
    domain = "api.semanticscholar.org"
    default_delay = 4.0

    def detect_peer_review(self, doc_type: str) -> str:
        cleaned_type = str(doc_type).lower().replace(" ", "")
        if "journalarticle" in cleaned_type:
            return "Likely"
        if any(t in cleaned_type for t in ["article", "proceedings", "journal"]):
            return "Yes"
        return "N/A"

    def setup_pacing(self):
        """Write the delay the credential buys into the shared pacing dict.

        Re-runnable, and it has to be: the pipeline empties this dict at the start
        of every run to undo the 429 escalation, which removes this entry too.
        The old guard -- ``self.domain in self.pacing_delays`` -- then read as
        "this source is not paced at all" and left the discount unapplied, so a
        keyed operator paced every run after the first at the unkeyed 4 s.
        """
        if semantic_scholar_key(self.settings):
            self.pacing_delays[self.domain] = 1.0

    @classmethod
    def unavailable_reason(cls, settings: Dict[str, Any]) -> str:
        """The key is not a speed-up here, it is the difference between a source
        and a zero.

        Without one this endpoint's shared pool rate-limits the run into a
        blocked source a few requests in. Measured on a full run: three 429s,
        `Max retries exceeded. Blocking source.`, and a `Semantic Scholar: 0` in
        the reply that reads exactly like a source that was asked and found
        nothing.
        """
        if semantic_scholar_key(settings):
            return ""
        return (
            "no API key. Set SEMANTIC_SCHOLAR_API_KEY in the environment, or "
            "settings.api_keys.semantic_scholar in config.json."
        )

    def get_headers(self) -> Dict[str, str]:
        headers = super().get_headers()
        s2_key = semantic_scholar_key(self.settings)
        if s2_key:
            headers["x-api-key"] = s2_key
        return headers

    def fetch(self, anchors: List[str], tech_strings: List[str], limit: int = 50) -> List[Dict[str, Any]]:
        query = " ".join(keyword_terms(anchors, tech_strings))
        with self.lock:
            self.query_history.append({"Source": self.SOURCE_NAME, "Query": query})
        start_year = self.settings.get('start_year', 2021)
        s2_url = "https://api.semanticscholar.org/graph/v1/paper/search"

        articles = []
        offset = 0
        page_size = 100

        while len(articles) < limit:
            max_limit = min(limit - len(articles), page_size)
            params = {
                "query": query,
                "limit": max_limit,
                "offset": offset,
                "year": f"{start_year}-",
                "fields": "title,abstract,url,year,citationCount,publicationTypes,externalIds,journal,venue,authors"
            }

            data = self._make_request(s2_url, params=params, timeout=15)
            if not data:
                break

            papers = data.get('data', [])
            if not papers:
                break

            for i in papers:
                pub_types = i.get('publicationTypes', [])
                if not pub_types or not any(t in ['Editorial', 'News', 'Review'] for t in pub_types):
                    journal_info = i.get('journal') or {}
                    venue_name = journal_info.get('name') or i.get('venue') or "Unknown Venue"

                    doc_type = ", ".join(pub_types) if pub_types else "N/A"
                    articles.append({
                        "Title": i.get('title') or "Unknown Title",
                        "Authors": listed_authors(i.get('authors')),
                        "Abstract": i.get('abstract') or "",
                        "Year": i.get('year') or "N/A",
                        "URL": i.get('url') or "",
                        "Source": self.SOURCE_NAME,
                        "Citations": i.get('citationCount') or 0,
                        "Citations_Source": "semantic_scholar" if i.get('citationCount') is not None else "",
                        "DOI": (i.get('externalIds') or {}).get('DOI') or "",
                        "Type": doc_type,
                        "Peer_Reviewed": self.detect_peer_review(doc_type),
                        "Venue": venue_name
                    })

            offset += len(papers)
            if len(papers) < max_limit or offset >= 1000:
                break

        return articles[:limit]
