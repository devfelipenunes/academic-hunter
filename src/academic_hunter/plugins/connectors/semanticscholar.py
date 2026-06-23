import os
import logging
from typing import List, Dict, Any
from .base import BaseConnector

logger = logging.getLogger("academic_hunter.connectors")


class SemanticScholarConnector(BaseConnector):
    fetch_suffix = "semantic_scholar"
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
        api_keys = self.settings.get('api_keys', {})
        s2_key = os.environ.get('SEMANTIC_SCHOLAR_API_KEY') or api_keys.get('semantic_scholar') or self.settings.get('semantic_scholar_api_key')
        if s2_key and self.domain in self.pacing_delays:
            self.pacing_delays[self.domain] = 1.0

    def get_headers(self) -> Dict[str, str]:
        headers = super().get_headers()
        api_keys = self.settings.get('api_keys', {})
        s2_key = os.environ.get('SEMANTIC_SCHOLAR_API_KEY') or api_keys.get('semantic_scholar') or self.settings.get('semantic_scholar_api_key')
        if s2_key:
            headers["x-api-key"] = s2_key
        return headers

    def fetch(self, anchors: List[str], tech_strings: List[str], limit: int = 50) -> List[Dict[str, Any]]:
        query = f'{" ".join(anchors[:3])} {" ".join(tech_strings[:2])}'
        with self.lock:
            self.query_history.append({"Source": "SemanticScholar", "Query": query})
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
                "fields": "title,abstract,url,year,citationCount,publicationTypes,externalIds,journal,venue"
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
                        "Title": i.get('title', "Unknown Title"),
                        "Abstract": i.get('abstract') or "",
                        "Year": i.get('year', "N/A"),
                        "URL": i.get('url', ""),
                        "Source": "SemanticScholar",
                        "Citations": i.get('citationCount', 0),
                        "DOI": i.get('externalIds', {}).get('DOI'),
                        "Type": doc_type,
                        "Peer_Reviewed": self.detect_peer_review(doc_type),
                        "Venue": venue_name
                    })

            offset += len(papers)
            if len(papers) < max_limit or offset >= 1000:
                break

        return articles[:limit]
