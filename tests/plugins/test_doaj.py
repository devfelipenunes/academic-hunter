"""Tests for DOAJ connector."""
import pytest
from unittest.mock import MagicMock
from academic_hunter.plugins.connectors.doaj import DoajConnector


@pytest.fixture
def connector():
    conn = DoajConnector(cache=MagicMock(), settings={}, query_history=[], lock=MagicMock(), semaphore=MagicMock(), use_cache=False)
    conn._make_request = MagicMock()
    return conn


def test_doaj_fetch_empty_response(connector):
    """Returns empty list when no results."""
    connector._make_request.return_value = {"results": [], "total": 0}
    results = connector.fetch(["anchor"], ["tech"], limit=10)
    assert results == []


def test_doaj_fetch_returns_papers(connector):
    """Returns parsed papers from DOAJ response."""
    connector._make_request.return_value = {
        "results": [
            {
                "bibjson": {
                    "title": "DOAJ Paper Title",
                    "abstract": "This is the abstract of the paper.",
                    "year": "2024",
                    "journal": {"title": "Journal of Science"},
                    "identifier": [{"type": "doi", "id": "10.1000/doaj_test"}],
                    "link": [{"url": "https://example.com/paper"}],
                }
            },
            {
                "bibjson": {
                    "title": "Second Paper",
                    "abstract": "",
                    "year": "2023",
                    "journal": {},
                    "identifier": [],
                    "link": [],
                }
            },
        ],
        "total": 2,
    }
    results = connector.fetch(["anchor"], ["tech"], limit=10)
    assert len(results) == 2
    assert results[0]["Title"] == "DOAJ Paper Title"
    assert results[0]["Abstract"] == "This is the abstract of the paper."
    assert results[0]["DOI"] == "10.1000/doaj_test"
    assert results[0]["Source"] == "DOAJ"
    assert results[0]["URL"] == "https://example.com/paper"
    assert results[0]["Venue"] == "Journal of Science"
    assert results[1]["Title"] == "Second Paper"
    assert results[1]["DOI"] is None
    assert results[1]["URL"] == ""


def test_doaj_fetch_respects_limit(connector):
    """Stops fetching when limit is reached."""
    many_results = []
    for i in range(30):
        many_results.append({
            "bibjson": {"title": f"Paper {i}", "year": "2024", "journal": {"title": "J"}, "identifier": []},
        })
    connector._make_request.return_value = {"results": many_results, "total": 30}
    results = connector.fetch(["anchor"], ["tech"], limit=5)
    assert len(results) == 5


def test_doaj_fetch_no_data(connector):
    """Returns empty list when _make_request returns None."""
    connector._make_request.return_value = None
    results = connector.fetch(["anchor"], ["tech"], limit=10)
    assert results == []


def test_doaj_resolve_abstract_found(connector):
    """resolve_abstract_by_doi returns abstract when found."""
    connector._make_request.return_value = {
        "results": [{"bibjson": {"abstract": "Resolved abstract content."}}]
    }
    abstract = connector.resolve_abstract_by_doi("10.1000/test")
    assert abstract == "Resolved abstract content."


def test_doaj_resolve_abstract_not_found(connector):
    """resolve_abstract_by_doi returns empty string when DOI not found."""
    connector._make_request.return_value = {"results": []}
    abstract = connector.resolve_abstract_by_doi("10.1000/missing")
    assert abstract == ""


def test_doaj_resolve_abstract_error(connector):
    """resolve_abstract_by_doi returns empty string on error."""
    connector._make_request.side_effect = Exception("API Error")
    abstract = connector.resolve_abstract_by_doi("10.1000/test")
    assert abstract == ""
