"""A JSON ``null`` is a missing value, not the word "None".

``i.get('yearPublished', "N/A")`` guards only against the key being *absent*.
When the key is present and null -- which is what these APIs send for a record
that has no year, no DOI, no venue -- the default never applies, ``None`` travels
on as the value, and the exporter writes it: ``PY  - None`` in the RIS, ``year =
{None}`` in the BibTeX, an empty-looking cell in the CSV that is the string
``None``.

Measured across the connectors, the pattern sits on about twenty lines, and not
only on the year: title, abstract, URL and DOI have the same exposure.

Inside the pipeline this was already absorbed -- ``FIELD_SCHEMA`` in
``core/models/schema.py`` maps a ``None`` year to ``"N/A"`` when the ``Paper`` is
built. What the tests below pin is the plugin contract, which is what anything
reading a connector's dict directly gets.
"""

import threading

import pytest

from academic_hunter.plugins.connectors.core_ac import CoreConnector
from academic_hunter.plugins.connectors.crossref import CrossrefConnector
from academic_hunter.plugins.connectors.doaj import DoajConnector
from academic_hunter.plugins.connectors.openalex import OpenAlexConnector
from academic_hunter.plugins.connectors.semanticscholar import SemanticScholarConnector

NULL_CORE = {
    "results": [
        {
            "title": None,
            "abstract": None,
            "yearPublished": None,
            "id": None,
            "citationCount": None,
            "doi": None,
            "type": None,
            "journals": None,
            "publisher": None,
        }
    ]
}

NULL_CROSSREF = {
    "message": {
        "items": [
            {
                "title": None,
                "container-title": None,
                "abstract": None,
                "type": None,
                "URL": None,
                "DOI": None,
                "is-referenced-by-count": None,
                "author": None,
            }
        ],
        "next-cursor": None,
    }
}

NULL_DOAJ = {
    "results": [
        {
            "bibjson": {
                "title": None,
                "abstract": None,
                "year": None,
                "journal": None,
                "identifier": None,
                "link": None,
            }
        }
    ]
}

NULL_OPENALEX = {
    "results": [
        {
            "display_name": None,
            "abstract_inverted_index": None,
            "publication_year": None,
            "doi": None,
            "id": None,
            "cited_by_count": None,
            "type": None,
            "primary_location": None,
        }
    ],
    "meta": None,
}

NULL_SEMANTIC_SCHOLAR = {
    "data": [
        {
            "title": None,
            "abstract": None,
            "year": None,
            "url": None,
            "citationCount": None,
            "externalIds": None,
            "publicationTypes": None,
            "journal": None,
            "venue": None,
        }
    ]
}


def collect(monkeypatch, cls, payload):
    made = cls(
        cache=None,
        settings={},
        query_history=[],
        lock=threading.RLock(),
        semaphore=threading.Semaphore(1),
        use_cache=False,
    )
    monkeypatch.setattr(made, "_make_request", lambda url, **kwargs: payload)
    return made.fetch(["ledger"], ["throughput"], limit=1)[0]


@pytest.mark.parametrize(
    "cls,payload",
    [
        (CoreConnector, NULL_CORE),
        (CrossrefConnector, NULL_CROSSREF),
        (DoajConnector, NULL_DOAJ),
        (OpenAlexConnector, NULL_OPENALEX),
        (SemanticScholarConnector, NULL_SEMANTIC_SCHOLAR),
    ],
    ids=["core", "crossref", "doaj", "openalex", "semantic_scholar"],
)
class TestANullRecord:
    def test_the_year_is_the_placeholder(self, monkeypatch, cls, payload):
        """``{"yearPublished": None}`` used to come back as ``None``, and print as ``None``."""
        assert collect(monkeypatch, cls, payload)["Year"] == "N/A"

    def test_the_title_is_the_placeholder(self, monkeypatch, cls, payload):
        assert collect(monkeypatch, cls, payload)["Title"] == "Unknown Title"

    def test_the_venue_is_the_placeholder(self, monkeypatch, cls, payload):
        assert collect(monkeypatch, cls, payload)["Venue"] == "Unknown Venue"

    def test_the_text_fields_are_empty_and_not_the_word_none(self, monkeypatch, cls, payload):
        record = collect(monkeypatch, cls, payload)

        assert record["Abstract"] == ""
        assert record["URL"] == ""
        assert record["DOI"] == ""

    def test_no_field_carries_the_string_none(self, monkeypatch, cls, payload):
        """The sweep, rather than the field: this is the shape the defect took."""
        record = collect(monkeypatch, cls, payload)

        offenders = {
            key: value for key, value in record.items() if value is None or "None" in str(value)
        }
        assert offenders == {}, f"a null leaked into the record as a value: {offenders}"
