"""Tests for ClinicalTrials.gov search tool."""

import pytest
from unittest.mock import patch, MagicMock
from academic_hunter.interfaces.mcp.tools.clinical_trials import search_clinical_trials
from academic_hunter.interfaces.mcp.exceptions import MCPToolError


async def test_search_clinical_trials(mock_ctx):
    """Returns clinical trial results."""
    mock_response = {
        "studies": [
            {
                "protocolSection": {
                    "identificationModule": {"briefTitle": "Alzheimer's Drug Trial", "nctId": "NCT12345678"},
                    "statusModule": {"overallStatus": "RECRUITING", "startDateStruct": {"date": "2024-01"}},
                    "designModule": {"phases": ["PHASE3"]},
                    "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Pfizer"}},
                }
            }
        ]
    }
    with patch("academic_hunter.interfaces.mcp.tools.clinical_trials.requests.get") as m_get:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = mock_response
        m_get.return_value = resp
        result = await search_clinical_trials(mock_ctx, "Alzheimer", limit=5)
        assert "Alzheimer" in result
        assert "NCT12345678" in result
        assert "RECRUITING" in result
        mock_ctx.info.assert_called()


async def test_search_clinical_trials_no_results(mock_ctx):
    """Graceful when no results."""
    with patch("academic_hunter.interfaces.mcp.tools.clinical_trials.requests.get") as m_get:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"studies": []}
        m_get.return_value = resp
        result = await search_clinical_trials(mock_ctx, "zzzzznothing")
        assert "No clinical trials found" in result


async def test_search_clinical_trials_error(mock_ctx):
    """Handles API errors."""
    with patch("academic_hunter.interfaces.mcp.tools.clinical_trials.requests.get") as m_get:
        m_get.side_effect = Exception("API error")
        with pytest.raises(MCPToolError):
            await search_clinical_trials(mock_ctx, "test")
        mock_ctx.error.assert_called()
