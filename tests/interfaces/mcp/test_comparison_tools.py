"""Tests for compare_papers tool."""
import pytest
from unittest.mock import patch, MagicMock


async def test_compare_papers_both_found(mock_ctx, mock_openalex, openalex_work, openalex_response):
    """Returns comparison with metadata from OpenAlex."""
    from academic_hunter.interfaces.mcp.tools.comparison import compare_papers

    response_a = openalex_response(
        openalex_work(
            "Paper A Title",
            2024,
            "This paper discusses blockchain technology for payments.",
        )
    )
    response_b = openalex_response(
        openalex_work(
            "Paper B Title",
            2023,
            "A study on blockchain and distributed ledger systems payments.",
        )
    )

    with patch("academic_hunter.interfaces.mcp.tools.comparison.requests.get") as m_get:
        m_get.side_effect = [response_a, response_b]
        result = await compare_papers(mock_ctx, "10.1000/a", "10.1000/b")

    assert "Paper A Title" in result
    assert "Paper B Title" in result
    assert "10.1000/a" in result
    assert "10.1000/b" in result
    assert "Shared Keywords" in result
    assert "blockchain" in result
    assert "payment" in result or "payments" in result


async def test_compare_papers_fallback_arxiv(mock_ctx, mock_openalex):
    """Falls back to AcademicHunter when OpenAlex fails for an arXiv DOI."""
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


async def test_compare_papers_not_found(mock_ctx, mock_openalex):
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


async def test_compare_papers_no_overlap(mock_ctx, mock_openalex, openalex_work, openalex_response):
    """Shows no-shared-keywords message when there's no overlap."""
    from academic_hunter.interfaces.mcp.tools.comparison import compare_papers

    response_a = openalex_response(
        openalex_work("Quantum Computing", 2024, "Qubits superposition quantum gates entanglement.")
    )
    response_b = openalex_response(
        openalex_work("Ancient Rome", 2023, "Roman empire colosseum gladiators latin literature.")
    )

    with patch("academic_hunter.interfaces.mcp.tools.comparison.requests.get") as m_get:
        m_get.side_effect = [response_a, response_b]
        result = await compare_papers(mock_ctx, "10.1000/quantum", "10.1000/rome")

    assert "No significant keyword overlap" in result


async def test_compare_papers_shared_keywords_empty_abstract(
    mock_ctx, mock_openalex, openalex_work, openalex_response
):
    """Handles a work OpenAlex holds without an abstract."""
    from academic_hunter.interfaces.mcp.tools.comparison import compare_papers

    response_a = openalex_response(openalex_work("Paper A", 2024))
    response_b = openalex_response(openalex_work("Paper B", 2023))

    with patch("academic_hunter.interfaces.mcp.tools.comparison.requests.get") as m_get:
        m_get.side_effect = [response_a, response_b]
        with patch("academic_hunter.interfaces.mcp.tools.comparison.AcademicHunter") as m_h:
            m_h.return_value.fetch_abstract_by_doi.return_value = ""
            result = await compare_papers(mock_ctx, "10.1000/a", "10.1000/b")

    assert "Paper A" in result
    assert "Paper B" in result
    assert "*Not found*" in result
