"""The citation count was paid for and thrown away.

The OpenAlex and Crossref DOI lookups download the whole work record — the
count arrives on the same response as the abstract — and only the abstract was
read from it. CORE returns ``citationCount`` on the object its fetch loop
already walks, and the connector wrote a hardcoded ``0`` over it.

These tests read the records the connectors already receive, with no network.
"""

import threading
from unittest.mock import MagicMock

import pytest

from academic_hunter.plugins.connectors.base import BaseConnector
from academic_hunter.plugins.connectors.core_ac import CoreConnector
from academic_hunter.plugins.connectors.crossref import CrossrefConnector
from academic_hunter.plugins.connectors.openalex import OpenAlexConnector


def connector(cls, settings=None):
    instance = cls.__new__(cls)
    instance.settings = settings or {"user_email": "test@example.com"}
    instance.cache = None
    instance.use_cache = False
    instance.lock = threading.RLock()
    instance.semaphore = threading.Semaphore(2)
    instance.query_history = []
    instance.last_request_by_domain = {}
    instance.pacing_delays = {}
    instance.blocked_sources = set()
    instance._make_request = MagicMock(return_value=None)
    return instance


def test_openalex_resolves_the_abstract_and_the_count_from_one_response():
    instance = connector(OpenAlexConnector)
    instance._make_request.return_value = {
        "abstract_inverted_index": {"Blockchain": [0], "in": [1], "finance": [2]},
        "cited_by_count": 75,
    }

    metadata = instance.resolve_metadata_by_doi("10.1000/x")

    assert metadata == {"Abstract": "Blockchain in finance", "Citations": 75}
    assert instance._make_request.call_count == 1
    assert instance.resolve_abstract_by_doi("10.1000/x") == "Blockchain in finance"


def test_openalex_without_a_count_reports_none_rather_than_zero():
    """An absent field is "not known here", and a zero would be a claim no one made."""
    instance = connector(OpenAlexConnector)
    instance._make_request.return_value = {"abstract_inverted_index": {"Text": [0]}}

    assert instance.resolve_metadata_by_doi("10.1000/x") == {"Abstract": "Text"}


def test_openalex_reports_a_genuine_zero_as_a_zero():
    instance = connector(OpenAlexConnector)
    instance._make_request.return_value = {"cited_by_count": 0}

    assert instance.resolve_metadata_by_doi("10.1000/x") == {"Citations": 0}


def test_crossref_resolves_the_abstract_and_the_count_from_one_response():
    instance = connector(CrossrefConnector)
    instance._make_request.return_value = {
        "message": {"abstract": "<jats:p>Crossref text</jats:p>", "is-referenced-by-count": 43}
    }

    assert instance.resolve_metadata_by_doi("10.1000/x") == {
        "Abstract": "Crossref text",
        "Citations": 43,
    }
    assert instance.resolve_abstract_by_doi("10.1000/x") == "Crossref text"


def test_core_reports_the_count_it_already_returns():
    from academic_hunter.core.infra.config import HunterConfig

    instance = connector(CoreConnector, settings=HunterConfig().settings)
    instance._make_request.return_value = {
        "results": [
            {
                "id": 1,
                "title": "A work",
                "abstract": "Text",
                "yearPublished": 2021,
                "doi": "10.1000/x",
                "citationCount": 43,
            }
        ]
    }

    papers = instance.fetch(["blockchain"], ["ai"], limit=1)

    assert papers[0]["Citations"] == 43
    assert papers[0]["Citations_Source"] == "core"


def test_a_connector_with_no_doi_lookup_answers_with_nothing():
    """ArXiv, CORE and Semantic Scholar inherit this; the enricher skips them by priority."""
    assert BaseConnector.resolve_metadata_by_doi(MagicMock(), "10.1000/x") == {}


def test_a_source_that_reports_no_count_carries_no_provenance():
    from academic_hunter.core.infra.config import HunterConfig

    instance = connector(CoreConnector, settings=HunterConfig().settings)
    instance._make_request.return_value = {
        "results": [{"id": 1, "title": "A work", "yearPublished": 2021, "doi": "10.1000/x"}]
    }

    papers = instance.fetch(["blockchain"], ["ai"], limit=1)

    assert papers[0]["Citations"] == 0
    assert papers[0]["Citations_Source"] == ""


def test_the_batch_asks_about_fifty_dois_per_request():
    instance = connector(OpenAlexConnector)
    instance._make_request.return_value = {"results": []}
    dois = [f"10.1000/{i}" for i in range(120)]

    instance.fetch_citations_by_dois(dois)

    assert instance._make_request.call_count == 3
    params = [call.kwargs["params"] for call in instance._make_request.call_args_list]
    assert [p["per_page"] for p in params] == [50, 50, 20]
    for request in params:
        assert request["filter"].startswith("doi:")
        assert request["select"] == "doi,cited_by_count"
        assert request["mailto"] == "test@example.com"


def test_the_batch_sorts_its_keys_so_the_cache_still_hits():
    """The cache is keyed on the serialised params, so an unsorted list never repeats."""
    instance = connector(OpenAlexConnector)
    instance._make_request.return_value = {"results": []}

    instance.fetch_citations_by_dois(["10.1000/c", "10.1000/a", "10.1000/b"])

    assert instance._make_request.call_args.kwargs["params"]["filter"] == "doi:10.1000/a|10.1000/b|10.1000/c"


def test_the_batch_returns_counts_keyed_by_normalised_doi():
    instance = connector(OpenAlexConnector)
    instance._make_request.return_value = {
        "results": [
            {"doi": "https://doi.org/10.1000/X", "cited_by_count": 75},
            {"doi": "https://doi.org/10.1000/y", "cited_by_count": 0},
        ]
    }

    counts = instance.fetch_citations_by_dois(["10.1000/x", "10.1000/y"])

    assert counts == {"10.1000/x": 75, "10.1000/y": 0}


def test_a_failed_chunk_degrades_instead_of_aborting_the_backfill():
    instance = connector(OpenAlexConnector)
    instance._make_request.side_effect = [RuntimeError("429"), {"results": [{"doi": "10.1000/b", "cited_by_count": 3}]}]

    counts = instance.fetch_citations_by_dois(["10.1000/a", "10.1000/b"], chunk_size=1)

    assert counts == {"10.1000/b": 3}


@pytest.mark.parametrize("value", [None, "unexpected"])
def test_a_malformed_response_is_read_as_no_answer(value):
    instance = connector(OpenAlexConnector)
    instance._make_request.return_value = value

    assert instance.fetch_citations_by_dois(["10.1000/a"]) == {}
