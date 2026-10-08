"""The Crossref abstract reaches the corpus as text, from either path.

Measured over the items already in the request cache: 17 152 of 17 152 Crossref
abstracts carry JATS markup. The enrichment path stripped it and the collection
path stored the field as it arrived, so the same record entered the corpus two
ways -- ``<jats:p xml:lang="en">Ledgers &amp; throughput</jats:p>`` against
``Ledgers & throughput``.

That is not cosmetic. ``Abstract`` is what gets embedded and keyword-matched,
so a tag sitting across a term splits the term and the markup counts towards
neither. The two copies of one paper then scored differently for a reason no
reading of the config would show.
"""

import threading

from academic_hunter.plugins.connectors.crossref import CrossrefConnector

JATS = '<jats:p xml:lang="en">Ledgers &amp; throughput</jats:p>'
PLAIN = "Ledgers & throughput"

CROSSREF_ITEM = {
    "title": ["Ledgers at scale"],
    "author": [{"family": "Lovelace", "given": "Ada"}],
    "container-title": ["Journal of Ledgers"],
    "abstract": JATS,
    "issued": {"date-parts": [[2024, 1, 1]]},
    "type": "journal-article",
    "DOI": "10.1234/ledger",
    "URL": "https://example.org/ledger",
    "is-referenced-by-count": 3,
}


def connector(monkeypatch, payload=None):
    made = CrossrefConnector(
        cache=None,
        settings={},
        query_history=[],
        lock=threading.RLock(),
        semaphore=threading.Semaphore(1),
        use_cache=False,
    )

    def make(url, **kwargs):
        return payload

    monkeypatch.setattr(made, "_make_request", make)
    return made


def test_the_collection_path_yields_text(monkeypatch):
    made = connector(monkeypatch, payload={"message": {"items": [CROSSREF_ITEM]}})

    papers = made.fetch(["ledger"], ["throughput"], limit=1)

    assert papers[0]["Abstract"] == PLAIN


def test_the_enrichment_path_yields_the_same_text():
    """The path that already cleaned must keep the entity decoding the other gained."""
    metadata = CrossrefConnector.work_metadata({"message": CROSSREF_ITEM})

    assert metadata["Abstract"] == PLAIN


def test_both_paths_agree_on_one_record(monkeypatch):
    """Two readings of one field is how one of them goes stale."""
    made = connector(monkeypatch, payload={"message": {"items": [CROSSREF_ITEM]}})

    collected = made.fetch(["ledger"], ["throughput"], limit=1)[0]["Abstract"]
    enriched = CrossrefConnector.work_metadata({"message": CROSSREF_ITEM})["Abstract"]

    assert collected == enriched


def test_an_entity_the_parser_does_not_know_is_left_alone():
    """``html.unescape`` leaves unknown entities intact rather than eating them."""
    text = CrossrefConnector.work_metadata(
        {"message": {"abstract": "<jats:p>&nosuch; &#65;</jats:p>"}}
    )["Abstract"]

    assert text == "&nosuch; A"


def test_a_record_with_no_abstract_yields_no_abstract(monkeypatch):
    """Absent stays absent: an empty key is not the same as a cleaned one."""
    item = {key: value for key, value in CROSSREF_ITEM.items() if key != "abstract"}
    made = connector(monkeypatch, payload={"message": {"items": [item]}})

    assert made.fetch(["ledger"], ["throughput"], limit=1)[0]["Abstract"] == ""
    assert "Abstract" not in CrossrefConnector.work_metadata({"message": item})


def test_a_null_abstract_does_not_crash_the_collection(monkeypatch):
    """``null`` is a shape Crossref sends, and ``re.sub`` on ``None`` is not a string."""
    made = connector(monkeypatch, payload={"message": {"items": [{**CROSSREF_ITEM, "abstract": None}]}})

    assert made.fetch(["ledger"], ["throughput"], limit=1)[0]["Abstract"] == ""
