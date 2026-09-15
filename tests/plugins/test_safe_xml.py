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
