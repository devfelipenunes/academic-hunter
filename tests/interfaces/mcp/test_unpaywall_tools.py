"""Tests for Unpaywall tool.

The HTTP call was extracted to ``plugins/fulltext/unpaywall.py`` so the pipeline
can reach it without importing the interface layer, which moves where the mock
has to point. The assertions are unchanged: they pin the tool's output format,
which is the behaviour worth protecting.
"""

from unittest.mock import MagicMock, patch

import pytest

from academic_hunter.interfaces.mcp.exceptions import MCPToolError
from academic_hunter.interfaces.mcp.tools.unpaywall import find_open_access


async def test_the_configured_address_is_used_when_none_is_passed(mock_ctx):
    """A hardcoded placeholder address cannot work, so there must not be one.

    The signature defaulted to ``me@example.com`` while the docstring called the
    argument "optional but recommended" -- and Unpaywall answers 422 to the
    documentation's own placeholder domains, so the tool could not run as
    shipped. Measured: it did not, in the first diagnostic.

    With no address passed, the configured one is used, resolved exactly as the
    full-text step resolves it, so one setting serves both.
    """
    config = MagicMock()
    config.fulltext_config.return_value = {"email": "researcher@university.edu"}

    with patch("academic_hunter.core.get_config", return_value=config):
        with patch("academic_hunter.plugins.fulltext.unpaywall.requests.get") as m_get:
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"is_oa": False, "oa_status": "closed"}
            m_get.return_value = resp
            await find_open_access(mock_ctx, "10.1234/test")

    assert m_get.call_args.kwargs["params"]["email"] == "researcher@university.edu"


async def test_the_refusal_names_the_key_to_set(mock_ctx):
    """When nothing usable is configured, the remedy has to be a real key."""
    config = MagicMock()
    config.fulltext_config.return_value = {"email": ""}

    with patch("academic_hunter.core.get_config", return_value=config):
        with patch("academic_hunter.plugins.fulltext.unpaywall.requests.get") as m_get:
            resp = MagicMock()
            resp.status_code = 422
            m_get.return_value = resp
            result = await find_open_access(mock_ctx, "10.1234/test")

    assert "settings.fulltext.email" in result, result
    assert "your@email.com" not in result, (
        "the remedy pointed at a placeholder address, which is the shape of the "
        "problem rather than the fix"
    )


async def test_find_open_access_oa(mock_ctx):
    """Returns OA status for an open-access paper."""
    mock_response = {
        "is_oa": True,
        "oa_status": "gold",
        "best_oa_location": {
            "url_for_pdf": "https://example.com/paper.pdf",
            "host_type": "publisher",
            "license": "cc-by",
            "version": "publishedVersion",
        },
    }
    with patch("academic_hunter.plugins.fulltext.unpaywall.requests.get") as m_get:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = mock_response
        m_get.return_value = resp
        result = await find_open_access(mock_ctx, "10.1234/test", "test@example.com")
        assert "✅ Yes" in result
        assert "https://example.com/paper.pdf" in result
        mock_ctx.info.assert_called()


async def test_find_open_access_closed(mock_ctx):
    """Returns OA status for a closed-access paper."""
    with patch("academic_hunter.plugins.fulltext.unpaywall.requests.get") as m_get:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"is_oa": False, "oa_status": "closed"}
        m_get.return_value = resp
        result = await find_open_access(mock_ctx, "10.1234/paywalled")
        assert "❌ No" in result


async def test_find_open_access_error(mock_ctx):
    """Handles API errors gracefully."""
    with patch("academic_hunter.plugins.fulltext.unpaywall.requests.get") as m_get:
        m_get.side_effect = Exception("API error")
        with pytest.raises(MCPToolError):
            await find_open_access(mock_ctx, "10.1234/test")
        mock_ctx.error.assert_called()
