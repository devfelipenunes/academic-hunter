import logging
from typing import List, Dict, Any
from .base import BaseConnector

logger = logging.getLogger("academic_hunter.connectors")


class DblpConnector(BaseConnector):
    fetch_suffix = "dblp"
    is_keyword_only = True
    domain = "dblp.org"
    default_delay = 1.5

    def detect_peer_review(self, doc_type: str) -> str:
        cleaned_type = str(doc_type).lower()
        if any(t in cleaned_type for t in ["article", "proceedings", "journal"]):
            return "Yes"
        return "N/A"

    def fetch(self, anchors: List[str], tech_strings: List[str], limit: int = 50) -> List[Dict[str, Any]]:
        query = f"{' '.join(anchors[:3])} {' '.join(tech_strings[:2])}"
        with self.lock:
            self.query_history.append({"Source": "DBLP", "Query": query})

        articles = []
        first = 0
        page_size = 100
        dblp_url = "https://dblp.org/search/pub/api"

        while len(articles) < limit:
            max_limit = min(limit - len(articles), page_size)
            params = {"q": query, "format": "json", "h": max_limit, "f": first}

            data = self._make_request(dblp_url, params=params, timeout=15)
            if not data:
                break

            hits = data.get('result', {}).get('hits', {}).get('hit', [])
            if not hits:
                break

            for hit in hits:
                info = hit.get('info', {})
                title = info.get('title', 'Unknown Title')
                year = info.get('year', 'N/A')
                venue = info.get('venue', 'Unknown Venue')
                doi = info.get('doi')
                url = info.get('url', '')

                doc_type = info.get('type', 'article')
                articles.append({
                    "Title": title,
                    "Abstract": "",
                    "Year": year,
                    "URL": url,
                    "Source": "DBLP",
                    "Citations": 0,
                    "DOI": doi,
                    "Type": doc_type,
                    "Peer_Reviewed": self.detect_peer_review(doc_type),
                    "Venue": venue
                })

            first += len(hits)
            if len(hits) < max_limit:
                break

        return articles[:limit]
