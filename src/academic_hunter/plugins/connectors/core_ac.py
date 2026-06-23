import os
import logging
from typing import List, Dict, Any
from .base import BaseConnector

logger = logging.getLogger("academic_hunter.connectors")


class CoreConnector(BaseConnector):
    fetch_suffix = "core_ac"
    is_keyword_only = False
    domain = "api.core.ac.uk"
    default_delay = 3.0

    def detect_peer_review(self, doc_type: str) -> str:
        cleaned_type = str(doc_type).lower()
        if any(t in cleaned_type for t in ["article", "proceedings", "journal"]):
            return "Yes"
        return "N/A"

    def get_headers(self) -> Dict[str, str]:
        headers = super().get_headers()
        api_keys = self.settings.get('api_keys', {})
        core_key = os.environ.get('CORE_API_KEY') or api_keys.get('core') or self.settings.get('core_api_key')
        if core_key:
            headers["ApiKey"] = core_key
        return headers

    def fetch(self, anchors: List[str], tech_strings: List[str], limit: int = 30) -> List[Dict[str, Any]]:
        anchor_group = ' OR '.join([f'"{t}"' for t in anchors])
        tech_group = ' OR '.join([f'"{t}"' for t in tech_strings])
        query = f"title:({anchor_group}) AND abstract:({tech_group})"
        with self.lock:
            self.query_history.append({"Source": "CORE", "Query": query})

        articles = []
        offset = 0
        page_size = 100
        core_url = "https://api.core.ac.uk/v3/search/works"

        while len(articles) < limit:
            max_limit = min(limit - len(articles), page_size)
            params = {"q": query, "limit": max_limit, "offset": offset}

            data = self._make_request(core_url, params=params, timeout=20)
            if not data:
                break

            results = data.get('results', [])
            if not results:
                break

            for i in results:
                journals = i.get('journals') or []
                first_journal = journals[0] if journals and journals[0] else {}
                venue_name = i.get('publisher') or first_journal.get('title') or "Unknown Venue"

                doc_type = i.get('type', "journal-article")
                articles.append({
                    "Title": i.get('title', "Unknown Title"),
                    "Abstract": i.get('abstract', ""),
                    "Year": i.get('yearPublished', "N/A"),
                    "URL": f"https://core.ac.uk/works/{i.get('id')}" if i.get('id') else "",
                    "Source": "CORE",
                    "Citations": 0,
                    "DOI": i.get('doi'),
                    "Type": doc_type,
                    "Peer_Reviewed": self.detect_peer_review(doc_type),
                    "Venue": venue_name
                })

            offset += len(results)
            if len(results) < max_limit:
                break

        return articles[:limit]
