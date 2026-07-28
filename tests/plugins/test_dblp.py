"""Tests for DBLP connector."""
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from academic_hunter.plugins.connectors.dblp import DblpConnector


@pytest.fixture
def connector():
    conn = DblpConnector(cache=MagicMock(), settings={}, query_history=[], lock=MagicMock(), semaphore=MagicMock(), use_cache=False)
    conn._make_request = MagicMock()
    return conn


def test_dblp_fetch_empty_response(connector):
    """Returns empty list when no results."""
    connector._make_request.return_value = {"result": {"hits": {"hit": [], "@total": 0}}}
    results = connector.fetch(["anchor"], ["tech"], limit=10)
    assert results == []


def test_dblp_fetch_returns_papers(connector):
    """Returns parsed papers from DBLP response."""
    connector._make_request.return_value = {
        "result": {"hits": {"hit": [
            {"info": {
                "title": "Blockchain Paper Title",
                "year": "2024",
                "venue": "Journal of Blockchain",
                "doi": "10.1000/test",
                "url": "https://dblp.org/rec/123",
                "type": "article",
            }},
            {"info": {
                "title": "Second Paper Title",
                "year": "2023",
                "venue": "Conference on CS",
                "doi": None,
                "url": "",
                "type": "inproceedings",
            }},
        ], "@total": 2}}}
    results = connector.fetch(["anchor"], ["tech"], limit=10)
    assert len(results) == 2
    assert results[0]["Title"] == "Blockchain Paper Title"
    assert results[0]["Year"] == "2024"
    assert results[0]["DOI"] == "10.1000/test"
    assert results[0]["Source"] == "DBLP"
    assert results[1]["Title"] == "Second Paper Title"
    assert results[1]["DOI"] is None
    assert results[1]["Source"] == "DBLP"


def test_dblp_fetch_respects_limit(connector):
    """Stops fetching when limit is reached."""
    many_hits = []
    for i in range(50):
        many_hits.append({"info": {"title": f"Paper {i}", "year": "2024", "venue": "V", "type": "article"}})
    connector._make_request.return_value = {"result": {"hits": {"hit": many_hits, "@total": 50}}}
    results = connector.fetch(["anchor"], ["tech"], limit=5)
    assert len(results) == 5


def test_dblp_fetch_no_data(connector):
    """Returns empty list when _make_request returns None."""
    connector._make_request.return_value = None
    results = connector.fetch(["anchor"], ["tech"], limit=10)
    assert results == []


def test_dblp_detect_peer_review_article():
    """detect_peer_review returns 'Yes' for articles."""
    conn = DblpConnector(cache=MagicMock(), settings={}, query_history=[], lock=MagicMock(), semaphore=MagicMock(), use_cache=False)
    assert conn.detect_peer_review("article") == "Yes"
    assert conn.detect_peer_review("proceedings") == "Yes"
    assert conn.detect_peer_review("journal") == "Yes"
    assert conn.detect_peer_review("phdthesis") == "N/A"
    assert conn.detect_peer_review("book") == "N/A"
