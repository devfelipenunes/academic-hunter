"""O que as APIs devolvem de verdade, e não o que seria conveniente.

Cada teste aqui fixa uma resposta com a forma que o provedor realmente usa —
incluindo os casos que o código tratava por truthiness ou por `.get(k, default)`.
"""

from unittest.mock import MagicMock, patch

import pytest


def _epmc_response(papers):
    response = MagicMock()
    response.json.return_value = {"hitCount": len(papers), "resultList": {"result": papers}}
    return response


async def _epmc_report(mock_ctx, **fields):
    from academic_hunter.interfaces.mcp.tools.europepmc import search_europepmc

    paper = {
        "title": "A study",
        "authorString": "A. Author",
        "firstPublicationDate": "2024-01-01",
        "source": "MED",
        **fields,
    }
    with patch("requests.get", return_value=_epmc_response([paper])):
        return await search_europepmc(mock_ctx, query="ledgers")


async def test_europe_pmc_badges_an_open_paper(mock_ctx):
    assert "[OA]" in await _epmc_report(mock_ctx, isOpenAccess="Y")


async def test_europe_pmc_does_not_badge_a_closed_one(mock_ctx):
    """`isOpenAccess` comes as the strings "Y" and "N".

    Used for its truthiness, `"N"` is a non-empty string and therefore true — so
    every closed-access paper was badged open.
    """
    report = await _epmc_report(mock_ctx, isOpenAccess="N")

    assert "[OA]" not in report, report


async def test_europe_pmc_without_the_field_badges_nothing(mock_ctx):
    report = await _epmc_report(mock_ctx)

    assert "[OA]" not in report, report


async def test_unpaywall_falls_back_when_the_pdf_field_is_null(mock_ctx):
    """`.get("url_for_pdf", fallback)` returns the fallback only when the key is
    **absent**.

    Unpaywall sends `"url_for_pdf": null` on locations it knows only as a landing
    page, so the URL it did provide was dropped and the lookup reported no link.
    """
    from academic_hunter.interfaces.mcp.tools.unpaywall import find_open_access

    record = {
        "is_oa": True,
        "oa_status": "green",
        "best_oa_location": {
            "url_for_pdf": None,
            "url": "https://repository.example.org/handle/1",
            "host_type": "repository",
            "version": "acceptedVersion",
        },
    }

    with patch(
        "academic_hunter.interfaces.mcp.tools.unpaywall.fetch_record", return_value=record
    ):
        report = await find_open_access(mock_ctx, doi="10.1234/abc")

    assert "https://repository.example.org/handle/1" in report


# ── ORCID ───────────────────────────────────────────────────────────────────


def _orcid_response(record):
    response = MagicMock()
    response.json.return_value = record
    return response


BASE_RECORD = {
    "person": {
        "name": {
            "given-names": {"value": "Ada"},
            "family-name": {"value": "Lovelace"},
        }
    },
    "activities-summary": {
        "employments": {
            "affiliation-group": [
                {
                    "summaries": [
                        {
                            "employment-summary": {
                                "organization": {"name": "Analytical Engines"},
                                "role-title": "Programmer",
                            }
                        }
                    ]
                }
            ]
        }
    },
}


async def _orcid_report(mock_ctx, record):
    from academic_hunter.interfaces.mcp.tools.orcid import lookup_orcid

    with patch("requests.get", return_value=_orcid_response(record)):
        return await lookup_orcid(mock_ctx, orcid_id="0000-0002-1825-0097")


async def test_orcid_survives_an_explicitly_null_credit_name(mock_ctx):
    """`{"credit-name": None}.get("credit-name", {})` returns None, not `{}`.

    The default only applies when the key is absent, so the next `.get` was a
    call on `None` and the whole lookup failed.
    """
    record = {
        **BASE_RECORD,
        "person": {**BASE_RECORD["person"], "name": {
            **BASE_RECORD["person"]["name"], "credit-name": None,
        }},
    }

    report = await _orcid_report(mock_ctx, record)

    assert "Ada Lovelace" in report, report


async def test_orcid_reads_the_affiliations_it_publishes(mock_ctx):
    """Employments live under `activities-summary`, not under `person`.

    Read from `person`, the section was always empty — the record has the data
    and the tool reported none.
    """
    report = await _orcid_report(mock_ctx, BASE_RECORD)

    assert "Analytical Engines" in report, report


# ── Lens ────────────────────────────────────────────────────────────────────


def _lens_post(captured, data=None):
    def post(url, json=None, headers=None, timeout=None):
        captured["headers"] = headers
        response = MagicMock()
        response.json.return_value = {"data": data or []}
        return response

    return post


async def test_the_patent_search_sends_the_token_the_api_requires(mock_ctx, monkeypatch):
    """Lens requires `Authorization: Bearer ...` on every request.

    The call sent `Content-Type` and nothing else, so every search was a 401 —
    and the module docstring's "1,000 requests/day with token" described a
    capability the tool had no path to.
    """
    from academic_hunter.interfaces.mcp.tools.lens import search_patents

    monkeypatch.setenv("LENS_API_KEY", "secret-token")
    captured = {}

    with patch("academic_hunter.interfaces.mcp.tools.lens.requests.post", _lens_post(captured)):
        await search_patents(mock_ctx, query="ledgers")

    assert captured["headers"].get("Authorization") == "Bearer secret-token"


async def test_without_a_token_it_says_which_one_is_missing(mock_ctx, monkeypatch):
    """A bare 401 does not tell anyone what to configure."""
    from academic_hunter.interfaces.mcp.exceptions import DiscoveryError
    from academic_hunter.interfaces.mcp.tools.lens import search_patents

    monkeypatch.delenv("LENS_API_KEY", raising=False)

    with patch("academic_hunter.core.get_config", return_value=MagicMock(settings={})):
        with pytest.raises(DiscoveryError) as exc:
            await search_patents(mock_ctx, query="ledgers")

    assert "LENS_API_KEY" in str(exc.value), str(exc.value)


async def test_the_token_can_come_from_the_config_instead(mock_ctx, monkeypatch):
    from academic_hunter.interfaces.mcp.tools.lens import search_patents

    monkeypatch.delenv("LENS_API_KEY", raising=False)
    config = MagicMock(settings={"api_keys": {"lens": "from-config"}})
    captured = {}

    with patch("academic_hunter.core.get_config", return_value=config), \
         patch("academic_hunter.interfaces.mcp.tools.lens.requests.post", _lens_post(captured)):
        await search_patents(mock_ctx, query="ledgers")

    assert captured["headers"].get("Authorization") == "Bearer from-config"


# ── OpenAIRE ────────────────────────────────────────────────────────────────


def _openaire_response(oaf):
    response = MagicMock()
    response.json.return_value = {
        "response": {"results": {"result": [{"metadata": {"oaf:entity": {"oaf:result": oaf}}}]}}
    }
    return response


async def _openaire_report(mock_ctx, oaf):
    from academic_hunter.interfaces.mcp.tools.openaire import search_openaire

    with patch("requests.get", return_value=_openaire_response(oaf)):
        return await search_openaire(mock_ctx, query="ledgers")


async def test_openaire_reads_a_single_valued_field(mock_ctx):
    """The XML→JSON conversion gives a **dict** when a field has one value.

    `oaf.get("title", [])` then iterated the dict's *keys* — the strings
    `"@classid"` and `"$"` — and called `.get` on them. The `project` field a few
    lines below already guards against exactly this: the guard was written once
    and was needed in five places.
    """
    oaf = {
        "title": {"@classid": "main title", "$": "A single-valued title"},
        "creator": {"@classid": "author", "$": "Ada Lovelace"},
        "dateofacceptance": {"$": "2024-01-01"},
    }

    report = await _openaire_report(mock_ctx, oaf)

    assert "A single-valued title" in report, report
    assert "Ada Lovelace" in report, report


async def test_openaire_reads_a_multi_valued_field(mock_ctx):
    """The same field comes back as a list when there are several values."""
    oaf = {
        "title": [
            {"@classid": "subtitle", "$": "A subtitle"},
            {"@classid": "main title", "$": "The real title"},
        ],
        "creator": [{"$": "Ada"}, {"$": "Grace"}],
    }

    report = await _openaire_report(mock_ctx, oaf)

    assert "The real title" in report, report
    assert "Ada; Grace" in report, report


# ── bioRxiv / medRxiv ───────────────────────────────────────────────────────


def _biorxiv_page(items, cursor):
    response = MagicMock()
    response.json.return_value = {
        "messages": [{"status": "ok", "cursor": cursor, "count": len(items)}],
        "collection": items,
    }
    return response


async def test_biorxiv_follows_the_cursor_to_find_a_match(mock_ctx):
    """The API answers by date range, and one page does not cover 90 days.

    Only the first page was read, so "no matching preprints found" could mean
    "none on the page we happened to read" — reported as a result about the whole
    window the tool announces.
    """
    from academic_hunter.interfaces.mcp.tools.biorxiv import search_biorxiv

    pages = [
        _biorxiv_page([{"title": "Something unrelated", "abstract": ""}], cursor=100),
        _biorxiv_page([{"title": "Ledger methods", "abstract": ""}], cursor=200),
        # An empty page ends the walk. Without it the mock runs out of responses
        # and the resulting StopIteration inside the coroutine hangs the test.
        _biorxiv_page([], cursor=200),
    ]

    with patch("requests.get", side_effect=pages):
        report = await search_biorxiv(mock_ctx, query="ledger")

    assert "Ledger methods" in report, report


async def test_biorxiv_stops_when_the_cursor_stops_moving(mock_ctx):
    """A cursor that does not advance would repeat the same page forever."""
    from academic_hunter.interfaces.mcp.tools.biorxiv import search_biorxiv

    page = _biorxiv_page([{"title": "Something unrelated", "abstract": ""}], cursor=0)

    with patch("requests.get", return_value=page) as m_get:
        report = await search_biorxiv(mock_ctx, query="ledger")

    assert "No matching preprints" in report
    assert m_get.call_count <= 2, f"the loop did not stop: {m_get.call_count} pages"


# ── o health e um store que não responde ────────────────────────────────────


async def test_a_store_that_cannot_be_read_makes_the_status_degrade(mock_ctx):
    """`collection_stats` returns `{"count": 0, "error": ...}` on an access failure.

    Health read only `count`, so a database that could not be opened was
    indistinguishable from an empty one — and the probe a container orchestrator
    relies on answered `status: ok`.
    """
    from academic_hunter.interfaces.mcp.health import _probe_components

    broken = MagicMock()
    broken.collection_stats.return_value = {
        "name": "papers",
        "count": 0,
        "error": "disk I/O error",
    }

    with patch("academic_hunter.interfaces.mcp.health._get_vector_store", return_value=broken), \
         patch("academic_hunter.core.get_config", return_value=MagicMock()):
        status = _probe_components()

    assert status["vector_store"]["available"] is False, status
    assert status["status"] != "ok", f"a broken store reported {status['status']!r}"


async def test_an_empty_store_is_still_healthy(mock_ctx):
    """Absent is not broken: a collection that does not exist yet is fine."""
    from academic_hunter.interfaces.mcp.health import _probe_components

    empty = MagicMock()
    empty.collection_stats.return_value = {"name": "papers", "count": 0, "status": "empty"}

    with patch("academic_hunter.interfaces.mcp.health._get_vector_store", return_value=empty), \
         patch("academic_hunter.core.get_config", return_value=MagicMock()):
        status = _probe_components()

    assert status["vector_store"]["available"] is True, status
