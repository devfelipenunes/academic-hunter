import logging
import urllib.parse
import xml.etree.ElementTree as ET
from typing import List, Dict, Any
from .base import BaseConnector

logger = logging.getLogger("academic_hunter.connectors")


class ArxivConnector(BaseConnector):
    fetch_suffix = "arxiv"
    is_keyword_only = False
    domain = "export.arxiv.org"
    default_delay = 3.0

    def detect_peer_review(self, doc_type: str) -> str:
        return "No (Preprint)"

    def fetch(self, anchors: List[str], tech_strings: List[str], limit: int = 50) -> List[Dict[str, Any]]:
        anchor_group = ' OR '.join([f'all:"{t}"' for t in anchors])
        tech_group = ' OR '.join([f'all:{t}' for t in tech_strings])
        query = f"({anchor_group}) AND ({tech_group})"
        with self.lock:
            self.query_history.append({"Source": "ArXiv", "Query": query})

        articles = []
        start = 0
        page_size = 100
        arxiv_url = "http://export.arxiv.org/api/query?"

        while len(articles) < limit:
            max_results = min(limit - len(articles), page_size)
            url = f"{arxiv_url}search_query={urllib.parse.quote(query)}&start={start}&max_results={max_results}"

            try:
                cached_xml = self.cache.get(url) if (self.use_cache and self.cache) else None
                if cached_xml:
                    xml_data = cached_xml
                else:
                    # Use _raw_request from BaseConnector for pacing and concurrency
                    resp = self._raw_request(url, timeout=20)
                    if resp is None:
                        break
                    xml_data = resp.text
                    if self.use_cache and self.cache:
                        self.cache.set(url, xml_data)

                root = ET.fromstring(xml_data)
                ns = {'atom': 'http://www.w3.org/2005/Atom'}

                entries = root.findall('atom:entry', ns)
                if not entries:
                    break

                for e in entries:
                    title_elem = e.find('atom:title', ns)
                    summary_elem = e.find('atom:summary', ns)
                    published_elem = e.find('atom:published', ns)
                    id_elem = e.find('atom:id', ns)

                    doc_type = "preprint"
                    articles.append({
                        "Title": title_elem.text.strip().replace('\n', ' ') if title_elem is not None and title_elem.text else "N/A",
                        "Abstract": summary_elem.text.strip().replace('\n', ' ') if summary_elem is not None and summary_elem.text else "",
                        "Year": published_elem.text[:4] if published_elem is not None and published_elem.text else "N/A",
                        "URL": id_elem.text if id_elem is not None and id_elem.text else "",
                        "Source": "ArXiv",
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
