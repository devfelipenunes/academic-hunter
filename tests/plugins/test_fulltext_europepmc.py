"""Europe PMC full text, and the chain that makes it a fallback.

Why this source exists: the PMC website answers any non-browser client with
HTML, so the `/pdf/` URL pattern recovers nothing (measured). Europe PMC's REST
API serves the same articles as JATS XML — fetchable, and already sectioned.
"""

from unittest.mock import MagicMock, patch

import pytest

from academic_hunter.core.ports.fulltext import (
    ExtractedDocument,
    FullTextConfigError,
    FullTextTransientError,
    NoOpenAccessVersion,
)
from academic_hunter.plugins.fulltext.europepmc import (
    EuropePmcSource,
    jats_to_text,
)
from academic_hunter.plugins.fulltext.sources import (
    ChainFullTextSource,
    UnpaywallPdfSource,
)

SEARCH = "academic_hunter.plugins.fulltext.europepmc.requests.get"

def _long(sentence, times=12):
    """Padding so the flattened text clears the 500-char text-layer threshold."""
    return " ".join([sentence] * times)


JATS = f"""<?xml version="1.0"?>
<article>
  <front><article-meta>
    <abstract><p>{_long("Sharing data benefits science.")}</p></abstract>
  </article-meta></front>
  <body>
    <sec><title>Introduction</title><p>{_long("Sharing information facilitates science.")}</p></sec>
    <sec><title>Methods</title><p>{_long("We surveyed 1000 researchers.")}</p>
      <sec><title>Participants</title><p>{_long("All were funded by a grant.")}</p></sec>
    </sec>
    <sec><title>Results</title><p>{_long("Most shared their data.")}</p></sec>
  </body>
</article>""".encode()


def response(status=200, payload=None, content=b""):
    mock = MagicMock()
    mock.status_code = status
    mock.content = content
    mock.json.return_value = payload if payload is not None else {}
    return mock


def hunt_response(pmcid="PMC123"):
    return response(200, {"resultList": {"result": [{"pmcid": pmcid}]}})


# ── JATS → text ─────────────────────────────────────────────────────────────


def test_headings_survive_as_lines():
    """The chunker finds sections by the shape of a line, so the titles have to
    come through as lines — that is what makes the `section` metadata reliable
    instead of guessed."""
    text = jats_to_text(JATS)

    assert "Introduction\n" in text
    assert "Methods\n" in text
    assert "Results\n" in text


def test_the_abstract_comes_first_and_named():
    assert jats_to_text(JATS).startswith("Abstract\nSharing data benefits science.")


def test_nested_sections_keep_their_own_heading():
    """A subsection's text must not be swallowed into its parent.

    Walking every `<p>` under a section does exactly that, and loses the
    subsection's heading — the thing parsing JATS instead of a PDF buys.
    """
    text = jats_to_text(JATS)

    assert "Participants\n" in text, "the subsection heading was lost"
    assert "All were funded by a grant." in text
    assert "We surveyed 1000 researchers." in text, "the parent lost its own paragraph"


def test_malformed_xml_is_transient():
    with pytest.raises(FullTextTransientError):
        jats_to_text(b"<article><body>unclosed")


# ── locating the article ────────────────────────────────────────────────────


def test_find_pmcid_returns_the_identifier():
    with patch(SEARCH, return_value=response(200, {"resultList": {"result": [{"pmcid": "PMC42"}]}})):
        assert EuropePmcSource().find_pmcid("10.1/x") == "PMC42"


def test_find_pmcid_returns_none_when_absent():
    with patch(SEARCH, return_value=response(200, {"resultList": {"result": []}})):
        assert EuropePmcSource().find_pmcid("10.1/x") is None


def test_find_pmcid_skips_results_without_one():
    payload = {"resultList": {"result": [{"id": "1"}, {"pmcid": "PMC7"}]}}
    with patch(SEARCH, return_value=response(200, payload)):
        assert EuropePmcSource().find_pmcid("10.1/x") == "PMC7"


# ── fetching ────────────────────────────────────────────────────────────────


def test_fetch_returns_the_sectioned_document():
    with patch(SEARCH, side_effect=[hunt_response(), response(200, content=JATS)]):
        document = EuropePmcSource().fetch("10.1/x")

    assert document.has_text_layer is True
    assert "Introduction" in document.text


def test_a_doi_without_a_pmcid_is_no_open_access():
    with patch(SEARCH, return_value=response(200, {"resultList": {"result": []}})):
        with pytest.raises(NoOpenAccessVersion):
            EuropePmcSource().fetch("10.1/x")


def test_a_404_on_the_full_text_is_no_open_access():
    with patch(SEARCH, side_effect=[hunt_response(), response(404)]):
        with pytest.raises(NoOpenAccessVersion):
            EuropePmcSource().fetch("10.1/x")


def test_a_server_error_is_transient():
    with patch(SEARCH, return_value=response(503)):
        with pytest.raises(FullTextTransientError):
            EuropePmcSource().fetch("10.1/x")


# ── the chain ───────────────────────────────────────────────────────────────


def source_returning(document=None, error=None, name="src"):
    def fn(doi):
        if error is not None:
            raise error
        return document

    fn.__name__ = name
    return fn


def good(text="Text " * 200):
    return ExtractedDocument(text=text, page_count=1, has_text_layer=True)


def test_the_first_source_that_works_wins():
    first = MagicMock(return_value=good())
    second = MagicMock(return_value=good("other"))

    result = ChainFullTextSource([first, second])("10.1/x")

    assert result.text.startswith("Text")
    second.assert_not_called()


def test_it_falls_through_to_the_next_source():
    """The reason the chain exists: Unpaywall knowing a paper is open says
    nothing about its being able to hand over a PDF."""
    first = source_returning(error=NoOpenAccessVersion("10.1/x"), name="unpaywall")
    second = MagicMock(return_value=good())

    assert ChainFullTextSource([first, second])("10.1/x").has_text_layer


def test_a_config_error_does_not_stop_the_chain():
    """The sources do not share configuration: a refused Unpaywall contact
    address leaves Europe PMC untouched."""
    first = source_returning(error=FullTextConfigError("bad e-mail"), name="unpaywall")
    second = MagicMock(return_value=good())

    assert ChainFullTextSource([first, second])("10.1/x").has_text_layer


def test_a_source_without_a_text_layer_falls_through():
    """A scan is not an answer when another source has the real text."""
    first = source_returning(
        document=ExtractedDocument(text="", page_count=9, has_text_layer=False),
        name="scanned",
    )
    second = MagicMock(return_value=good())

    assert ChainFullTextSource([first, second])("10.1/x").has_text_layer


def test_the_most_actionable_failure_is_raised():
    """All sources failed; the caller should learn about the fixable one."""
    chain = ChainFullTextSource([
        source_returning(error=NoOpenAccessVersion("x"), name="a"),
        source_returning(error=FullTextConfigError("bad e-mail"), name="b"),
    ])

    with pytest.raises(FullTextConfigError):
        chain("10.1/x")


def test_a_missing_copy_is_reported_when_that_is_all_there_was():
    chain = ChainFullTextSource([
        source_returning(error=NoOpenAccessVersion("x"), name="a"),
        source_returning(error=NoOpenAccessVersion("x"), name="b"),
    ])

    with pytest.raises(NoOpenAccessVersion):
        chain("10.1/x")


def test_an_unexpected_error_in_one_source_does_not_stop_the_chain():
    def explodes(doi):
        raise RuntimeError("nobody predicted this")

    explodes.__name__ = "boom"
    second = MagicMock(return_value=good())

    assert ChainFullTextSource([explodes, second])("10.1/x").has_text_layer


def test_a_chain_needs_a_source():
    with pytest.raises(ValueError):
        ChainFullTextSource([])


def test_unpaywall_pdf_source_locates_then_extracts():
    source = MagicMock()
    source.locate.return_value = "a-location"
    source.download.return_value = b"%PDF-fake"
    extractor = MagicMock()
    extractor.extract.return_value = good()

    result = UnpaywallPdfSource(source, extractor)("10.1/x")

    assert result.has_text_layer
    extractor.extract.assert_called_once_with(b"%PDF-fake")
