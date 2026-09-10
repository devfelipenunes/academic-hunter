"""Regression tests for the hunter's HTTP facade.

``AcademicHunter._make_request`` used to dispatch *every* URL through the
OpenAlex connector, whatever the destination. Pacing was unaffected — the
connector derives its domain from the URL — but the headers were not: OpenAlex
attaches ``Authorization: Bearer <key>``, so the OpenAlex API key travelled to
arXiv, Crossref and Semantic Scholar. It only fires when a key is configured,
which is why it went unnoticed.

These tests pin both directions: the key goes where it belongs, and it does not
go anywhere else.
"""

import json

import pytest
from unittest.mock import MagicMock

from academic_hunter import AcademicHunter

OPENALEX_KEY = "test-openalex-key-do-not-use"


@pytest.fixture
def hunter(tmp_path):
    config = {
        "settings": {
            "title_multiplier": 1.5,
            "score_precision": 1,
            "min_relevance_score": 3.0,
            "start_year": 2020,
            "user_email": "test@example.com",
            "api_keys": {"openalex": OPENALEX_KEY},
        },
        "anchors": {"cat": ["blockchain"]},
        "technical_strings": {"cat": ["latency"]},
        "technical_weights": {"blockchain": 5.0},
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    return AcademicHunter(config_path=str(config_path), output_dir=str(tmp_path / "out"))


@pytest.fixture
def captured(monkeypatch):
    """Capture the headers sent for each URL, without doing any network I/O."""
    seen = {}

    def fake_get(url, params=None, headers=None, timeout=None, **kwargs):
        seen[url] = dict(headers or {})
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {}
        return resp

    monkeypatch.setattr("academic_hunter.plugins.connectors.base.requests.get", fake_get)
    return seen


def _auth(headers):
    return {k: v for k, v in headers.items() if k.lower() in ("authorization", "x-api-key")}


def test_key_is_sent_to_its_own_host(hunter, captured):
    """The configured key must still reach OpenAlex — the fix is routing, not removal."""
    url = "https://api.openalex.org/works"
    hunter._make_request(url)

    assert captured[url].get("Authorization") == f"Bearer {OPENALEX_KEY}"


def test_key_is_not_sent_to_another_host(hunter, captured):
    """The whole point: a Crossref request must carry no OpenAlex credential."""
    url = "https://api.crossref.org/works"
    hunter._make_request(url)

    assert _auth(captured[url]) == {}, (
        f"credentials leaked to api.crossref.org: {_auth(captured[url])}"
    )


def test_key_is_not_sent_to_a_third_host(hunter, captured):
    """Same for Semantic Scholar, which routes to its own connector and key."""
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    hunter._make_request(url)

    assert _auth(captured[url]) == {}


def test_unknown_host_is_refused(hunter, captured):
    """No connector owns the host, so the request is refused rather than borrowed.

    The alternative — falling back to some connector's transport — is exactly
    the behaviour that leaked the key, so refusing is the contract.
    """
    with pytest.raises(ValueError, match="refusing to send"):
        hunter._make_request("https://example.invalid/works")

    assert captured == {}, "no request may leave for a host no connector owns"


def test_routing_does_not_break_arxiv(hunter, captured):
    """ArXiv keeps working through its own connector."""
    url = "http://export.arxiv.org/api/query"
    hunter._make_request(url)

    assert url in captured
    assert _auth(captured[url]) == {}
