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
