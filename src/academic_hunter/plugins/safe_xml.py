"""Parsing XML that arrived over the network."""

import codecs
import xml.etree.ElementTree as ET

_DTD_MARKERS = ("<!DOCTYPE", "<!ENTITY")

_BOMS = (
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)

_NO_BOM_SIGNATURES = (
    (b"\x3c\x00\x3f\x00", "utf-16-le"),
    (b"\x00\x3c\x00\x3f", "utf-16-be"),
    (b"\x3c\x00\x00\x00", "utf-32-le"),
    (b"\x00\x00\x00\x3c", "utf-32-be"),
)


def _decoded(data) -> str:
    """The document as text, in whatever encoding it actually arrived in.

    The DTD scan below only works on an ASCII-compatible encoding. A UTF-16
    document interleaves a NUL byte between every ASCII character, so after
    a ``utf-8`` decode the text reads ``<\\x00!\\x00D\\x00O\\x00...`` and the
    marker ``<!DOCTYPE`` never appears in it — while ``ET.fromstring``, which
    reads the BOM and the byte-order signature itself, parses the document and
    expands its entities anyway.

    Decoding here is what puts the scan and the parser on the same text. A
    UTF-16 document without a BOM is legal and expat still detects it from the
    ``<?`` signature, so the signature is checked too.
    """
    if isinstance(data, str):
        return data
    for bom, encoding in _BOMS:
        if data.startswith(bom):
            return data.decode(encoding, errors="replace")
    for signature, encoding in _NO_BOM_SIGNATURES:
        if data.startswith(signature):
            return data.decode(encoding, errors="replace")
    return data.decode("utf-8", errors="replace")


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
    text = _decoded(data)
    upper = text.upper()
    if any(marker in upper for marker in _DTD_MARKERS):
        raise ValueError("refusing XML that carries a DTD")
    return ET.fromstring(data)  # noqa: S314
