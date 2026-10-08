import html
import logging
import re
from typing import Any, Dict, List

from ...core.models.authors import crossref_authors
from .base import BaseConnector

logger = logging.getLogger("academic_hunter.connectors")

_JATS_TAG = re.compile(r"<[^>]+>")


def clean_abstract(value: Any) -> str:
    """A Crossref abstract as text: tags removed, entities decoded.

    Crossref stores the abstract as JATS XML, so what arrives is
    ``<jats:p xml:lang="en">Ledgers &amp; throughput</jats:p>``. The enrichment
    path stripped the tags and the collection path did not, so the same field
    reached the corpus two ways -- and the corpus is what gets embedded and
    keyword-matched, which is why the difference showed up as a scoring gap
    rather than as a cosmetic one. ``&amp;`` survived both: removing tags does
    not decode entities.

    Neither parser is a general XML reader on purpose. The strings come from
    third-party records, ``html.unescape`` leaves anything it does not recognise
    alone, and a title is not worth an XML dependency.
    """
    if not value:
        return ""
    return html.unescape(_JATS_TAG.sub("", str(value))).strip()


class CrossrefConnector(BaseConnector):
    fetch_suffix = "crossref"
    SOURCE_NAME = "Crossref"
    is_keyword_only = False
    domain = "api.crossref.org"
    default_delay = 1.5
    resolve_priority = 2

    def detect_peer_review(self, doc_type: str) -> str:
        return "Yes"

    def resolve_metadata_by_doi(self, doi: str) -> Dict[str, Any]:
        try:
            url = f"https://api.crossref.org/works/{doi}"
            email = self.settings.get('user_email', 'academic_hunter@example.com')
            data = self._make_request(url, params={"mailto": email}, timeout=10)
            return self.work_metadata(data)
        except Exception as e:
            logger.warning("Crossref metadata lookup failed for %s: %s", doi, e)
        return {}

    def find_published_version(self, title: str, authors: str = "") -> Dict[str, Any]:
        """Ask Crossref whether this title has a record that is not the preprint.

        A bibliographic query, not a DOI lookup: the whole question is which
        record the work has under a DOI nobody here knows. The answer is the
        candidate list as it came, unranked and unfiltered — which of them is the
        published version is a decision, and it is made in
        :mod:`academic_hunter.core.models.published_version` rather than here, so
        the rule is testable without an HTTP stub and the connector stays a
        translator of one API's shape.

        ``authors`` is accepted and not sent: Crossref's bibliographic search is
        over the reference text, and passing names into it narrows the recall of
        the only query that can find the record at all. The names are needed to
        *accept* an answer, which happens here only after the answer arrives.
        """
        if not str(title or "").strip():
            return {"title": title, "candidates": []}
        email = self.settings.get('user_email', 'academic_hunter@example.com')
        data = self._make_request(
            "https://api.crossref.org/works",
            params={
                "query.bibliographic": title,
                "rows": 5,
                "mailto": email,
            },
            timeout=15,
        )
        message = data.get('message') if isinstance(data, dict) else None
        items = message.get('items') if isinstance(message, dict) else None
        candidates = []
        for item in (items if isinstance(items, list) else []):
            if not isinstance(item, dict):
                continue
            titles = item.get('title') or []
            venues = item.get('container-title') or []
            candidates.append({
                "DOI": item.get('DOI') or '',
                "Title": titles[0] if titles else "",
                "Authors": crossref_authors(item.get('author')),
                "Type": item.get('type') or '',
                "Venue": venues[0] if venues else "",
                "Year": self.work_year(item),
            })
        return {"title": title, "candidates": candidates}

    @staticmethod
    def work_year(item: Dict[str, Any]) -> Any:
        """The year a Crossref work record carries, from the first date it has.

        ``published-print`` first: a record that has both a print and an online
        date was published in print, and that is the year a citation carries.
        Then online, then ``issued``, then ``created`` — the order the connector
        has always used, extracted so the search for a published version reads
        the year the same way the search that found the paper does.
        """
        for key in ('published-print', 'published-online', 'issued', 'created'):
            section = item.get(key) or {}
            date_parts = section.get('date-parts') or []
            if date_parts and date_parts[0]:
                return date_parts[0][0]
        return "N/A"

    @staticmethod
    def work_metadata(data: Any) -> Dict[str, Any]:
        """Read what the pipeline needs out of one Crossref work record.

        ``is-referenced-by-count`` arrives in the same response as the abstract
        and was previously dropped. Absent stays absent: without the field there
        is no ``Citations`` key, which is not the same as reporting zero.
        """
        if not isinstance(data, dict):
            return {}
        message = data.get('message')
        if not isinstance(message, dict):
            return {}
        metadata: Dict[str, Any] = {}
        abstract_text = clean_abstract(message.get('abstract', ''))
        if abstract_text:
            metadata["Abstract"] = abstract_text
        authors = crossref_authors(message.get('author'))
        if authors:
            metadata["Authors"] = authors
        citations = message.get('is-referenced-by-count')
        if citations is not None:
            try:
                metadata["Citations"] = max(int(citations), 0)
            except (TypeError, ValueError):
                pass
        return metadata

    def fetch(self, anchors: List[str], tech_strings: List[str], limit: int = 50) -> List[Dict[str, Any]]:
        anchor_group = ' '.join([f'"{t}"' for t in anchors])
        tech_group = ' '.join([f'"{t}"' for t in tech_strings])
        query = f"({anchor_group}) AND ({tech_group})"
        with self.lock:
            self.query_history.append({"Source": self.SOURCE_NAME, "Query": query})

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

            items = (data.get('message') or {}).get('items') or []
            if not items:
                break

            for i in items:
                titles = i.get('title') or []
                title = titles[0] if titles else "Unknown Title"
                venues = i.get('container-title') or []
                venue = venues[0] if venues else "Unknown Venue"

                year = self.work_year(i)
                doc_type = i.get('type') or "journal-article"
                articles.append({
                    "Title": title,
                    "Authors": crossref_authors(i.get('author')),
                    "Abstract": clean_abstract(i.get('abstract')),
                    "Year": year,
                    "URL": i.get('URL') or "",
                    "Source": self.SOURCE_NAME,
                    "Citations": i.get('is-referenced-by-count') or 0,
                    "Citations_Source": "crossref" if i.get('is-referenced-by-count') is not None else "",
                    "DOI": i.get('DOI') or "",
                    "Type": doc_type,
                    "Peer_Reviewed": self.detect_peer_review(doc_type),
                    "Venue": venue
                })

            next_cursor = (data.get('message') or {}).get('next-cursor')
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor

        return articles[:limit]
