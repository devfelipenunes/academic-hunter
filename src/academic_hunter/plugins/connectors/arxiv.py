import logging
import urllib.parse
from typing import Any, Dict, List

from ...core.models.authors import join_authors
from ...core.models.utils import collapse_whitespace
from ..safe_xml import parse_xml
from .base import BaseConnector

logger = logging.getLogger("academic_hunter.connectors")


class ArxivConnector(BaseConnector):
    fetch_suffix = "arxiv"
    SOURCE_NAME = "ArXiv"
    is_keyword_only = False
    domain = "export.arxiv.org"
    default_delay = 3.0

    def detect_peer_review(self, doc_type: str) -> str:
        return "No (Preprint)"

    def fetch(self, anchors: List[str], tech_strings: List[str], limit: int = 50) -> List[Dict[str, Any]]:
        """Page through the ArXiv API, caching each page.

        A page is written to the cache only once ``parse_xml`` has accepted it.
        Caching first meant a malformed page — an HTML error body served with a
        200, which is what a proxy in front of the API returns — was stored under
        the query URL and read back by every later run, failing in the same place
        each time with the network, the one thing that would have fixed it, never
        consulted.
        """
        anchor_group = ' OR '.join([f'all:"{t}"' for t in anchors])
        tech_group = ' OR '.join([f'all:{t}' for t in tech_strings])
        query = f"({anchor_group}) AND ({tech_group})"
        with self.lock:
            self.query_history.append({"Source": self.SOURCE_NAME, "Query": query})

        articles = []
        start = 0
        page_size = 100
        arxiv_url = "https://export.arxiv.org/api/query?"

        while len(articles) < limit:
            max_results = min(limit - len(articles), page_size)
            url = f"{arxiv_url}search_query={urllib.parse.quote(query)}&start={start}&max_results={max_results}"

            try:
                cached_xml = self.cache.get(url) if (self.use_cache and self.cache) else None
                already_cached = bool(cached_xml)
                if already_cached:
                    xml_data = cached_xml
                else:
                    resp = self._raw_request(url, timeout=20)
                    if resp is None:
                        break
                    xml_data = resp.text

                root = parse_xml(xml_data)
                if not already_cached and self.use_cache and self.cache:
                    self.cache.set(url, xml_data)

                ns = {'atom': 'http://www.w3.org/2005/Atom'}

                entries = root.findall('atom:entry', ns)
                if not entries:
                    break

                for e in entries:
                    title_elem = e.find('atom:title', ns)
                    summary_elem = e.find('atom:summary', ns)
                    published_elem = e.find('atom:published', ns)
                    id_elem = e.find('atom:id', ns)
                    author_names = [
                        collapse_whitespace(name_elem.text)
                        for author_elem in e.findall('atom:author', ns)
                        for name_elem in author_elem.findall('atom:name', ns)
                        if name_elem is not None and name_elem.text
                    ]

                    doc_type = "preprint"
                    articles.append({
                        "Title": collapse_whitespace(title_elem.text) if title_elem is not None and title_elem.text else "N/A",
                        "Authors": join_authors(author_names),
                        "Abstract": collapse_whitespace(summary_elem.text) if summary_elem is not None and summary_elem.text else "",
                        "Year": published_elem.text[:4] if published_elem is not None and published_elem.text else "N/A",
                        "URL": id_elem.text if id_elem is not None and id_elem.text else "",
                        "Source": self.SOURCE_NAME,
                        "Citations": 0,
                        "Type": doc_type,
                        "Peer_Reviewed": self.detect_peer_review(doc_type),
                        "Venue": "ArXiv"
                    })

                start += len(entries)
                if len(entries) < max_results:
                    break
            except Exception as e:
                logger.error(f"ArXiv fetch error: {e}")
                break

        return articles[:limit]
