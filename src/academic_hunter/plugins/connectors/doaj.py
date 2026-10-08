import logging
import urllib.parse
from typing import Any, Dict, List

from .base import BaseConnector, keyword_terms, quoted_ors

logger = logging.getLogger("academic_hunter.connectors")


class DoajConnector(BaseConnector):
    fetch_suffix = "doaj"
    SOURCE_NAME = "DOAJ"
    is_keyword_only = True
    domain = "doaj.org"
    default_delay = 1.5
    resolve_priority = 1

    def detect_peer_review(self, doc_type: str) -> str:
        return "Yes"

    def resolve_metadata_by_doi(self, doi: str) -> Dict[str, Any]:
        try:
            url = f"https://doaj.org/api/search/articles/doi:{doi}"
            data = self._make_request(url, timeout=10)
            if data and data.get('results'):
                abstract = (data['results'][0].get('bibjson') or {}).get('abstract') or ''
                if abstract:
                    return {"Abstract": abstract}
        except Exception as e:
            logger.warning("DOAJ metadata lookup failed: %s", e)
        return {}

    def fetch(self, anchors: List[str], tech_strings: List[str], limit: int = 50) -> List[Dict[str, Any]]:
        query = quoted_ors(keyword_terms(anchors, tech_strings))
        with self.lock:
            self.query_history.append({"Source": self.SOURCE_NAME, "Query": query})

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

            results = data.get('results') or []
            if not results:
                break

            for res in results:
                bibjson = res.get('bibjson') or {}
                title = bibjson.get('title') or 'Unknown Title'
                abstract = bibjson.get('abstract') or ''
                year = bibjson.get('year') or 'N/A'
                journal = bibjson.get('journal') or {}
                venue = journal.get('title') or "Unknown Venue"

                doi = None
                for ident in bibjson.get('identifier') or []:
                    if ident.get('type') == 'doi':
                        doi = ident.get('id')
                        break

                article_url = ""
                for link in bibjson.get('link') or []:
                    if link.get('url'):
                        article_url = link.get('url')
                        break

                doc_type = "journal-article"
                articles.append({
                    "Title": title,
                    "Abstract": abstract,
                    "Year": year,
                    "URL": article_url,
                    "Source": self.SOURCE_NAME,
                    "Citations": 0,
                    "DOI": doi or "",
                    "Type": doc_type,
                    "Peer_Reviewed": self.detect_peer_review(doc_type),
                    "Venue": venue
                })

            page += 1
            if len(results) < max_limit:
                break

        return articles[:limit]
