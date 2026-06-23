import re
import logging
from typing import List, Dict, Any
from .base import BaseConnector

logger = logging.getLogger("academic_hunter.connectors")


class CrossrefConnector(BaseConnector):
    fetch_suffix = "crossref"
    is_keyword_only = False
    domain = "api.crossref.org"
    default_delay = 1.5
    resolve_priority = 2

    def detect_peer_review(self, doc_type: str) -> str:
        return "Yes"

    def resolve_abstract_by_doi(self, doi: str) -> str:
        try:
            url = f"https://api.crossref.org/works/{doi}"
            email = self.settings.get('user_email', 'academic_hunter@example.com')
            data = self._make_request(url, params={"mailto": email}, timeout=10)
            if data:
                abstract_text = data.get('message', {}).get('abstract', '')
                if abstract_text:
                    return re.sub(r'<[^>]+>', '', abstract_text).strip()
        except Exception:
            pass
        return ""

    def fetch(self, anchors: List[str], tech_strings: List[str], limit: int = 50) -> List[Dict[str, Any]]:
        anchor_group = ' '.join([f'"{t}"' for t in anchors])
        tech_group = ' '.join([f'"{t}"' for t in tech_strings])
        query = f"({anchor_group}) AND ({tech_group})"
        with self.lock:
            self.query_history.append({"Source": "Crossref", "Query": query})

        start_year = self.settings.get('start_year', 2021)
        user_email = self.settings.get('user_email', 'academic_hunter@example.com')
        crossref_url = "https://api.crossref.org/works"

        articles = []
        cursor = "*"

        while len(articles) < limit:
            rows = min(limit - len(articles), 100)
            params = {
                "query": query,
                "rows": rows,
                "cursor": cursor,
                "filter": f"type:journal-article,from-pub-date:{start_year}-01-01",
                "mailto": user_email
            }

            data = self._make_request(crossref_url, params=params, timeout=15)
            if not data:
                break

            items = data.get('message', {}).get('items', [])
            if not items:
                break

            for i in items:
                titles = i.get('title', [])
                title = titles[0] if titles else "Unknown Title"
                venues = i.get('container-title', [])
                venue = venues[0] if venues else "Unknown Venue"

                published_print = i.get('published-print') or {}
                date_parts = published_print.get('date-parts', [])
                year = date_parts[0][0] if date_parts and date_parts[0] else "N/A"
                if year == "N/A":
                    published_online = i.get('published-online') or {}
                    date_parts = published_online.get('date-parts', [])
                    year = date_parts[0][0] if date_parts and date_parts[0] else "N/A"
                if year == "N/A":
                    issued = i.get('issued') or {}
                    date_parts = issued.get('date-parts', [])
                    year = date_parts[0][0] if date_parts and date_parts[0] else "N/A"
                if year == "N/A":
                    created = i.get('created') or {}
                    date_parts = created.get('date-parts', [])
                    year = date_parts[0][0] if date_parts and date_parts[0] else "N/A"

                doc_type = i.get('type', "journal-article")
                articles.append({
                    "Title": title,
                    "Abstract": i.get('abstract', ""),
                    "Year": year,
                    "URL": i.get('URL', ""),
                    "Source": "Crossref",
                    "Citations": i.get('is-referenced-by-count', 0),
                    "DOI": i.get('DOI'),
                    "Type": doc_type,
                    "Peer_Reviewed": self.detect_peer_review(doc_type),
                    "Venue": venue
                })

            next_cursor = data.get('message', {}).get('next-cursor')
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor

        return articles[:limit]
