"""Tests for compare_papers tool."""
import pytest
from unittest.mock import patch, MagicMock


async def test_compare_papers_both_found(mock_ctx):
    """Returns comparison with metadata from Semantic Scholar."""
    from academic_hunter.interfaces.mcp.tools.comparison import compare_papers

    mock_response_a = MagicMock()
    mock_response_a.json.return_value = {
        "title": "Paper A Title",
        "year": 2024,
        "abstract": "This paper discusses blockchain technology for payments.",
    }

    mock_response_b = MagicMock()
    mock_response_b.json.return_value = {
        "title": "Paper B Title",
        "year": 2023,
        "abstract": "A study on blockchain and distributed ledger systems payments.",
    }

    with patch("academic_hunter.interfaces.mcp.tools.comparison.requests.get") as m_get:
        m_get.side_effect = [mock_response_a, mock_response_b]
        result = await compare_papers(mock_ctx, "10.1000/a", "10.1000/b")

    assert "Paper A Title" in result
    assert "Paper B Title" in result
    assert "10.1000/a" in result
    assert "10.1000/b" in result
    assert "Shared Keywords" in result
    assert "blockchain" in result
    assert "payment" in result or "payments" in result


async def test_compare_papers_fallback_arxiv(mock_ctx):
    """Falls back to AcademicHunter when Semantic Scholar fails for arXiv DOI."""
    from academic_hunter.interfaces.mcp.tools.comparison import compare_papers

    mock_fail = MagicMock()
    mock_fail.raise_for_status.side_effect = __import__("requests").HTTPError("Not found")

    with patch("academic_hunter.interfaces.mcp.tools.comparison.requests.get") as m_get:
        m_get.return_value = mock_fail
        with patch("academic_hunter.interfaces.mcp.tools.comparison.AcademicHunter") as m_h:
            instance = m_h.return_value
            instance.fetch_abstract_by_doi.return_value = "Title: arXiv paper abstract here."
            # Second call to fetch_abstract_by_doi for abstract_b also returns
            # But our mock needs to return for TWO calls
            instance.fetch_abstract_by_doi.side_effect = [
                "Title: arXiv paper abstract here.",
                "arXiv paper B abstract.",
            ]
            result = await compare_papers(mock_ctx, "10.48550/arXiv.1234", "10.48550/arXiv.5678")

    assert "arXiv paper" in result


async def test_compare_papers_invalid_doi(mock_ctx):
    """Raises DiscoveryError for invalid DOI format."""
    from academic_hunter.interfaces.mcp.tools.comparison import compare_papers
    from academic_hunter.interfaces.mcp.exceptions import DiscoveryError

    with pytest.raises(DiscoveryError):
        await compare_papers(mock_ctx, "not-a-doi", "10.1000/valid")


async def test_compare_papers_not_found(mock_ctx):
    """Raises DiscoveryError when neither source finds the paper."""
    from academic_hunter.interfaces.mcp.tools.comparison import compare_papers
    from academic_hunter.interfaces.mcp.exceptions import DiscoveryError

    mock_fail = MagicMock()
    mock_fail.raise_for_status.side_effect = __import__("requests").HTTPError("Not found")

    with patch("academic_hunter.interfaces.mcp.tools.comparison.requests.get") as m_get:
        m_get.return_value = mock_fail
        with patch("academic_hunter.interfaces.mcp.tools.comparison.AcademicHunter") as m_h:
            m_h.return_value.fetch_abstract_by_doi.return_value = None
            with pytest.raises(DiscoveryError):
                await compare_papers(mock_ctx, "10.1000/missing", "10.1000/also_missing")


async def test_compare_papers_no_overlap(mock_ctx):
    """Shows no-shared-keywords message when there's no overlap."""
    from academic_hunter.interfaces.mcp.tools.comparison import compare_papers

    mock_a = MagicMock()
    mock_a.json.return_value = {
        "title": "Quantum Computing",
        "year": 2024,
        "abstract": "Qubits superposition quantum gates entanglement.",
    }
    mock_b = MagicMock()
    mock_b.json.return_value = {
        "title": "Ancient Rome",
        "year": 2023,
        "abstract": "Roman empire colosseum gladiators latin literature.",
    }

    with patch("academic_hunter.interfaces.mcp.tools.comparison.requests.get") as m_get:
        m_get.side_effect = [mock_a, mock_b]
        result = await compare_papers(mock_ctx, "10.1000/quantum", "10.1000/rome")

    assert "No significant keyword overlap" in result


async def test_compare_papers_shared_keywords_empty_abstract(mock_ctx):
    """Handles empty abstracts gracefully."""
    from academic_hunter.interfaces.mcp.tools.comparison import compare_papers

    mock_a = MagicMock()
    mock_a.json.return_value = {"title": "Paper A", "year": 2024, "abstract": ""}
    mock_b = MagicMock()
    mock_b.json.return_value = {"title": "Paper B", "year": 2023, "abstract": None}

    with patch("academic_hunter.interfaces.mcp.tools.comparison.requests.get") as m_get:
        m_get.side_effect = [mock_a, mock_b]
        with patch("academic_hunter.interfaces.mcp.tools.comparison.AcademicHunter") as m_h:
            m_h.return_value.fetch_abstract_by_doi.return_value = ""
            result = await compare_papers(mock_ctx, "10.1000/a", "10.1000/b")

    assert "Paper A" in result
    assert "Paper B" in result
    assert "*Not found*" in result
