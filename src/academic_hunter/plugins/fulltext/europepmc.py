"""Europe PMC — the full text the PMC website will not hand over.

Measured: ``https://pmc.ncbi.nlm.nih.gov/articles/PMC…/pdf/`` answers **200 with
HTML** to a non-browser client, so scraping the PDF from PMC recovers nothing.
Europe PMC's REST API serves the same articles as JATS XML, which is fetchable,
and — unlike a PDF — already carries the section structure the chunker would
otherwise have to guess at from heading heuristics.

That makes this the fallback for the common case where Unpaywall knows a copy
exists but names no ``url_for_pdf``: a DOI resolver and a PMC landing page.
"""

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, Optional

import requests

from ...core.ports.fulltext import (
    ExtractedDocument,
    FullTextTransientError,
    NoOpenAccessVersion,
)

logger = logging.getLogger("academic_hunter.fulltext.europepmc")

SEARCH_API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
FULLTEXT_API = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"

DEFAULT_TIMEOUT = 25

#: Below this the XML carried no usable body (an abstract-only record).
MIN_TEXT_CHARS = 500


def _section_title(node: ET.Element) -> str:
    title = node.find("title")
    if title is None or not (title.text or "").strip():
        return ""
    return re.sub(r"\s+", " ", title.text).strip()


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _paragraphs(node: ET.Element) -> str:
    """Every ``<p>`` under ``node``, as plain text."""
    parts = [_clean("".join(p.itertext())) for p in node.iter("p")]
    return "\n\n".join(p for p in parts if p)


def _walk_sections(node: ET.Element, blocks: list) -> None:
    """Emit each section, then its subsections.

    Only the ``<p>`` children *directly* under a section belong to it: walking
    them all would swallow a subsection's text into its parent and lose the
    subsection's heading, which is the whole reason to parse JATS instead of a
    PDF.
    """
    for section in node.findall("sec"):
        title = _section_title(section)
        own = [
            _clean("".join(child.itertext()))
            for child in section
            if child.tag == "p"
        ]
        body = "\n\n".join(p for p in own if p)
        if body:
            blocks.append(f"{title}\n{body}" if title else body)
        _walk_sections(section, blocks)


def jats_to_text(xml_bytes: bytes) -> str:
    """Flatten JATS XML into text with its headings kept as lines.

    Headings are emitted as their own line on purpose: the chunker recognises
    section titles by shape, so preserving them is what gives every chunk a
    trustworthy ``section`` without a second parser.

    Raises:
        FullTextTransientError: the bytes are not parseable JATS.
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise FullTextTransientError(f"Europe PMC returned invalid XML: {e}") from e

    blocks = []

    abstract = root.find(".//abstract")
    if abstract is not None:
        body = _paragraphs(abstract)
        if body:
            blocks.append(f"Abstract\n{body}")

    body = root.find(".//body")
    if body is not None:
        _walk_sections(body, blocks)

    return "\n\n".join(blocks).strip()


class EuropePmcSource:
    """Full text from Europe PMC, as an :class:`ExtractedDocument`."""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout

    def find_pmcid(self, doi: str) -> Optional[str]:
        """The PMCID for a DOI, or None when Europe PMC does not hold it."""
        try:
            response = requests.get(
                SEARCH_API,
                params={"query": f'DOI:"{doi}"', "format": "json", "resultType": "core"},
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise FullTextTransientError(f"Europe PMC search failed: {e}") from e

        if response.status_code != 200:
            raise FullTextTransientError(
                f"Europe PMC search returned HTTP {response.status_code}"
            )

        try:
            results = (response.json().get("resultList") or {}).get("result") or []
        except ValueError as e:
            raise FullTextTransientError(f"Europe PMC returned invalid JSON: {e}") from e

        for result in results:
            pmcid = result.get("pmcid")
            if pmcid:
                return str(pmcid)
        return None

    def fetch(self, doi: str) -> ExtractedDocument:
        """The article's text, or ``NoOpenAccessVersion`` when it is not there.

        Raises:
            NoOpenAccessVersion: no PMCID, or no full text behind it.
            FullTextTransientError: the request failed.
        """
        pmcid = self.find_pmcid(doi)
        if not pmcid:
            raise NoOpenAccessVersion(doi)

        try:
            response = requests.get(
                FULLTEXT_API.format(pmcid=pmcid), timeout=self.timeout
            )
        except requests.RequestException as e:
            raise FullTextTransientError(f"Europe PMC full text failed: {e}") from e

        if response.status_code == 404:
            raise NoOpenAccessVersion(doi)
        if response.status_code != 200:
            raise FullTextTransientError(
                f"Europe PMC returned HTTP {response.status_code}"
            )

        text = jats_to_text(response.content)  # raises the domain error itself

        has_layer = len(text) >= MIN_TEXT_CHARS
        if not has_layer:
            logger.info("Europe PMC record %s yielded only %d chars.", pmcid, len(text))
        return ExtractedDocument(text=text, page_count=0, has_text_layer=has_layer)

    def __call__(self, doi: str) -> ExtractedDocument:
        return self.fetch(doi)
