"""Parsing XML that arrived over the network."""

import xml.etree.ElementTree as ET

_DTD_MARKERS = ("<!DOCTYPE", "<!ENTITY")


def parse_xml(data):
    """Parse XML, refusing a document that carries a DTD.

    `ET.fromstring` expands *internal* entities (it rejects external ones), so a
    hostile document can be a few hundred bytes and expand to megabytes. The same
    bytes also come back out of the request cache, which is read and reparsed
    without validation — so a poisoned entry keeps working after the network
    stops.

    Neither the arXiv Atom feed nor the Europe PMC payloads carry a DTD, so
    refusing one costs nothing legitimate.
    """
    text = data if isinstance(data, str) else data.decode("utf-8", errors="replace")
    upper = text.upper()
    if any(marker in upper for marker in _DTD_MARKERS):
        raise ValueError("refusing XML that carries a DTD")
    return ET.fromstring(data)
