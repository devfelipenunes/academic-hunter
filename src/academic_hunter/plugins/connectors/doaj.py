import logging
import urllib.parse
from typing import List, Dict, Any
from .base import BaseConnector

logger = logging.getLogger("academic_hunter.connectors")


class DoajConnector(BaseConnector):
    fetch_suffix = "doaj"
    is_keyword_only = True
    domain = "doaj.org"
    default_delay = 1.5
    resolve_priority = 1

    def detect_peer_review(self, doc_type: str) -> str:
        return "Yes"

    def resolve_abstract_by_doi(self, doi: str) -> str:
        try:
            url = f"https://doaj.org/api/search/articles/doi:{doi}"
            data = self._make_request(url, timeout=10)
            if data and data.get('results'):
                return data['results'][0].get('bibjson', {}).get('abstract', '')
        except Exception:
            pass
        return ""

    def fetch(self, anchors: List[str], tech_strings: List[str], limit: int = 50) -> List[Dict[str, Any]]:
        query = f"{' '.join(anchors[:3])} {' '.join(tech_strings[:2])}"
        with self.lock:
            self.query_history.append({"Source": "DOAJ", "Query": query})

        articles = []
        page = 1
        page_size = 100
        doaj_url = "https://doaj.org/api/search/articles"

        while len(articles) < limit:
            max_limit = min(limit - len(articles), page_size)
            url = f"{doaj_url}/{urllib.parse.quote(query)}"
            params = {"pageSize": max_limit, "page": page}

            data = self._make_request(url, params=params, timeout=15)
            if not data:
                break

            results = data.get('results', [])
            if not results:
                break

            for res in results:
                bibjson = res.get('bibjson', {})
                title = bibjson.get('title', 'Unknown Title')
                abstract = bibjson.get('abstract', '')
                year = bibjson.get('year', 'N/A')
                journal = bibjson.get('journal', {})
                venue = journal.get('title') or "Unknown Venue"

                # Extract DOI
                doi = None
                for ident in bibjson.get('identifier', []):
                    if ident.get('type') == 'doi':
                        doi = ident.get('id')
                        break

                # Extract URL
                article_url = ""
                for link in bibjson.get('link', []):
                    if link.get('url'):
                        article_url = link.get('url')
                        break

                doc_type = "journal-article"
                articles.append({
                    "Title": title,
                    "Abstract": abstract,
                    "Year": year,
                    "URL": article_url,
                    "Source": "DOAJ",
                    "Citations": 0,
                    "DOI": doi,
                    "Type": doc_type,
                    "Peer_Reviewed": self.detect_peer_review(doc_type),
                    "Venue": venue
                })

            page += 1
            if len(results) < max_limit:
                break

        return articles[:limit]
