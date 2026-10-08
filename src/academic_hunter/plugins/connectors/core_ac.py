import logging
from typing import Any, Dict, List

from ...core.infra.config import core_key
from .base import BaseConnector, quoted_ors

logger = logging.getLogger("academic_hunter.connectors")


class CoreConnector(BaseConnector):
    fetch_suffix = "core_ac"
    SOURCE_NAME = "CORE"
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
        key = core_key(self.settings)
        if key:
            headers["ApiKey"] = key
        return headers

    @classmethod
    def unavailable_reason(cls, settings: Dict[str, Any]) -> str:
        """This search endpoint requires a key, and answers 401 without one.

        Which the pipeline reported as ``CORE: 0`` -- the same number a source
        that was asked and found nothing produces. Measured over the runs on
        disk: the key was never configured, so the source has never contributed
        a paper, and every report read as though it had been consulted.
        """
        if core_key(settings):
            return ""
        return (
            "no API key. Set CORE_API_KEY in the environment, or "
            "settings.api_keys.core in config.json."
        )

    def fetch(self, anchors: List[str], tech_strings: List[str], limit: int = 30) -> List[Dict[str, Any]]:
        query = f"({quoted_ors(anchors)}) AND ({quoted_ors(tech_strings)})"
        with self.lock:
            self.query_history.append({"Source": self.SOURCE_NAME, "Query": query})

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

            results = data.get('results') or []
            if not results:
                break

            for i in results:
                journals = i.get('journals') or []
                first_journal = journals[0] if journals and journals[0] else {}
                venue_name = i.get('publisher') or first_journal.get('title') or "Unknown Venue"

                doc_type = i.get('type') or "journal-article"
                articles.append({
                    "Title": i.get('title') or "Unknown Title",
                    "Abstract": i.get('abstract') or "",
                    "Year": i.get('yearPublished') or "N/A",
                    "URL": f"https://core.ac.uk/works/{i.get('id')}" if i.get('id') else "",
                    "Source": self.SOURCE_NAME,
                    "Citations": i.get('citationCount') or 0,
                    "Citations_Source": "core" if i.get('citationCount') is not None else "",
                    "DOI": i.get('doi') or "",
                    "Type": doc_type,
                    "Peer_Reviewed": self.detect_peer_review(doc_type),
                    "Venue": venue_name
                })

            offset += len(results)
            if len(results) < max_limit:
                break

        return articles[:limit]
