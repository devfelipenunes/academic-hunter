import os
import logging
from typing import List, Dict, Any
from .base import BaseConnector

logger = logging.getLogger("academic_hunter.connectors")


class OpenAlexConnector(BaseConnector):
    fetch_suffix = "openalex"
    is_keyword_only = False
    domain = "api.openalex.org"
    default_delay = 1.5
    resolve_priority = 3

    def detect_peer_review(self, doc_type: str) -> str:
        cleaned_type = str(doc_type).lower()
        if any(t in cleaned_type for t in ["article", "proceedings", "journal"]):
            return "Yes"
        return "N/A"

    def get_headers(self) -> Dict[str, str]:
        headers = super().get_headers()
        api_keys = self.settings.get('api_keys', {})
        openalex_key = os.environ.get('OPENALEX_API_KEY') or api_keys.get('openalex') or self.settings.get('openalex_api_key')
        if openalex_key:
            headers["Authorization"] = f"Bearer {openalex_key}"
        return headers

    def resolve_abstract_by_doi(self, doi: str) -> str:
        try:
            url = f"https://api.openalex.org/works/https://doi.org/{doi}"
            email = self.settings.get('user_email', 'academic_hunter@example.com')
            data = self._make_request(url, params={"mailto": email}, timeout=10)
            if data:
                return self._decode_openalex_abstract(data.get('abstract_inverted_index', {}))
        except Exception:
            pass
        return ""

    def _decode_openalex_abstract(self, inverted_index) -> str:
        if not inverted_index: return ""
        try:
            max_pos = max(max(pos) for pos in inverted_index.values())
            words = [""] * (max_pos + 1)
            for word, positions in inverted_index.items():
                for pos in positions: words[pos] = word
            return " ".join(words).strip()
        except Exception:
            return ""

    def fetch(self, anchors: List[str], tech_strings: List[str], limit: int = 50) -> List[Dict[str, Any]]:
        email = self.settings.get('user_email', 'academic_hunter@example.com')
        anchor_q = ' OR '.join([f'"{a}"' for a in anchors])
        tech_q = ' OR '.join([f'"{t}"' for t in tech_strings])
        query = f"({anchor_q}) AND ({tech_q})"
        with self.lock:
            self.query_history.append({"Source": "OpenAlex", "Query": query})

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

            results = data.get('results', [])
            if not results:
                break

            for i in results:
                raw_doi = i.get('doi') or ""
                doi_clean = raw_doi.replace('https://doi.org/', '').replace('http://doi.org/', '').lower()
                abstract_text = self._decode_openalex_abstract(i.get('abstract_inverted_index', {}))

                primary_loc = i.get('primary_location') or {}
                source_info = primary_loc.get('source') or {}
                venue_name = source_info.get('display_name') or "Unknown Venue"

                doc_type = i.get('type', "article")
                articles.append({
                    "Title": i.get('display_name', "Unknown Title"),
                    "Abstract": abstract_text,
                    "Year": i.get('publication_year', "N/A"),
                    "URL": i.get('doi') or i.get('id') or "",
                    "Source": "OpenAlex",
                    "Citations": i.get('cited_by_count', 0),
                    "DOI": doi_clean,
                    "Type": doc_type,
                    "Peer_Reviewed": self.detect_peer_review(doc_type),
                    "Venue": venue_name
                })

            next_cursor = data.get('meta', {}).get('next_cursor')
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor

        return articles[:limit]
