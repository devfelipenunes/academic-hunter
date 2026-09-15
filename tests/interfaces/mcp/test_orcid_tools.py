"""Tests for ORCID lookup tool."""

from unittest.mock import MagicMock, patch

import pytest

from academic_hunter.interfaces.mcp.exceptions import MCPToolError
from academic_hunter.interfaces.mcp.tools.orcid import lookup_orcid


@pytest.mark.asyncio
async def test_lookup_orcid(mock_ctx):
    """Returns researcher profile with name and publications."""
    mock_response = {
        "person": {
            "name": {
                "given-names": {"value": "Ada"},
                "family-name": {"value": "Lovelace"},
                "credit-name": {"value": "Ada Lovelace"},
            },
        },
        # Employments live here, nested two levels deep — not under `person`,
        # which is where the tool looked and where this fixture used to put them.
        "activities-summary": {
            "employments": {
                "affiliation-group": [
                    {
                        "summaries": [
                            {
                                "employment-summary": {
                                    "organization": {"name": "University of Cambridge"},
                                    "department-name": "Mathematics",
                                    "role-title": "Professor",
                                }
                            }
                        ]
                    }
                ]
            },
            "works": {
                "group": [
                    {
                        "work-summary": [
                            {
                                "title": {"title": {"value": "Analytical Engine"}},
                                "publication-date": {"year": {"value": "1843"}},
                                "external-ids": {
                                    "external-id": [
                                        {
                                            "external-id-type": "doi",
                                            "external-id-value": "10.1000/analytical",
                                        }
                                    ]
                                },
                            }
                        ]
                    }
                ]
            }
        },
    }

    with patch("academic_hunter.interfaces.mcp.tools.orcid.requests.get") as m_get:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = mock_response
        m_get.return_value = resp
        result = await lookup_orcid(mock_ctx, "0000-0002-1825-0097")
        assert "Ada Lovelace" in result
        assert "University of Cambridge" in result
        assert "Analytical Engine" in result
        assert "10.1000" in result
        mock_ctx.info.assert_called()


async def test_lookup_orcid_error(mock_ctx):
    """Handles API errors gracefully."""
    with patch("academic_hunter.interfaces.mcp.tools.orcid.requests.get") as m_get:
        m_get.side_effect = Exception("API error")
        with pytest.raises(MCPToolError):
            await lookup_orcid(mock_ctx, "0000-0002-1825-0097")
        mock_ctx.error.assert_called()
