"""XML vindo da rede não pode expandir entidades.

`ET.fromstring` recusa entidades *externas* — então XXE clássico não funciona —
mas expande as *internas*, e é por aí que um documento de algumas centenas de
bytes vira megabytes alocados.
"""

import xml.etree.ElementTree as ET

import pytest

from academic_hunter.plugins.safe_xml import parse_xml

PLAIN = '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"/>'

BOMB = (
    '<?xml version="1.0"?>\n'
    '<!DOCTYPE feed [\n'
    '  <!ENTITY a "lollollollollol">\n'
    '  <!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">\n'
    ']>\n'
    '<feed xmlns="http://www.w3.org/2005/Atom"><title>&b;</title></feed>'
)

XXE = (
    '<?xml version="1.0"?>\n'
    '<!DOCTYPE feed [<!ENTITY x SYSTEM "file:///etc/hostname">]>\n'
    '<feed xmlns="http://www.w3.org/2005/Atom"><title>&x;</title></feed>'
)


def test_a_plain_document_parses():
    assert parse_xml(PLAIN).tag.endswith("feed")


def test_bytes_parse_like_text():
    assert parse_xml(PLAIN.encode()).tag.endswith("feed")


def test_an_entity_bomb_is_refused():
    with pytest.raises(ValueError, match="DTD"):
        parse_xml(BOMB)


def test_an_external_entity_is_refused_before_it_reaches_the_parser():
    with pytest.raises(ValueError, match="DTD"):
        parse_xml(XXE)


def test_a_lowercase_doctype_is_refused_too():
    """XML keywords are case-sensitive, but nobody attacking this will care."""
    with pytest.raises(ValueError, match="DTD"):
        parse_xml(PLAIN.replace("?>", "?>\n<!doctype feed>"))


def test_malformed_xml_still_raises_a_parse_error():
    with pytest.raises(ET.ParseError):
        parse_xml("<feed><unclosed></feed>")


def _as(encoding, text):
    return text.encode(encoding)


def test_a_utf16_bomb_is_refused():
    """The scan read the bytes as UTF-8, and the parser did not.

    In UTF-16 every ASCII character is followed by a NUL, so ``<!DOCTYPE`` is
    not a substring of the utf-8 decoding of the document — the marker check
    passed and ``ET.fromstring``, which reads the BOM itself, expanded the
    entities. Measured on the defect: one 319-character document, refused as
    UTF-8, parsed from UTF-16 and returned 1.5 million characters.
    """
    with pytest.raises(ValueError, match="DTD"):
        parse_xml(_as("utf-16", BOMB))


def test_a_utf16_bomb_without_a_bom_is_refused():
    """A BOM is optional, and expat detects the byte order from ``<?``."""
    with pytest.raises(ValueError, match="DTD"):
        parse_xml(_as("utf-16-le", '<?xml version="1.0"?>' + BOMB[BOMB.index("<!DOCTYPE") :]))


def test_a_utf32_bomb_is_refused():
    with pytest.raises(ValueError, match="DTD"):
        parse_xml(_as("utf-32", BOMB))


def test_a_utf16_document_without_a_dtd_still_parses():
    """Rejecting UTF-16 wholesale would cost legitimate payloads.

    The obvious way to close the hole — refusing anything that is not ASCII —
    breaks every feed served in UTF-16.
    """
    assert parse_xml(_as("utf-16", PLAIN)).tag.endswith("feed")
