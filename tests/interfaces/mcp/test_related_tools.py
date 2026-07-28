"""Tests for find_related_papers tool."""
import pytest
from unittest.mock import patch, MagicMock


async def test_find_related_papers_no_vector_store(mock_ctx):
    """Returns message when vector store is unavailable."""
    from academic_hunter.interfaces.mcp.tools.related import find_related_papers

    with patch("academic_hunter.interfaces.mcp.tools.related._get_vector_store") as m:
        m.return_value = None
        result = await find_related_papers(mock_ctx, "blockchain")
    assert "Vector store not available" in result


async def test_find_related_papers_no_results(mock_ctx):
    """Returns message when no results found."""
    from academic_hunter.interfaces.mcp.tools.related import find_related_papers

    mock_store = MagicMock()
    mock_store.query.return_value = []

    with patch("academic_hunter.interfaces.mcp.tools.related._get_vector_store") as m:
        m.return_value = mock_store
        result = await find_related_papers(mock_ctx, "nonexistent topic")
    assert "No related papers found" in result


async def test_find_related_papers_clamps_top_k(mock_ctx):
    """Clamps top_k to max 20."""
    from academic_hunter.interfaces.mcp.tools.related import find_related_papers

    mock_store = MagicMock()
    mock_store.query.return_value = []

    with patch("academic_hunter.interfaces.mcp.tools.related._get_vector_store") as m:
        m.return_value = mock_store
        await find_related_papers(mock_ctx, "test", top_k=50)
    # Should call with top_k=20 (clamped)
    args, kwargs = mock_store.query.call_args
    assert kwargs.get("top_k") == 20 or args[1] == 20


async def test_find_related_papers_returns_results(mock_ctx):
    """Returns formatted list of related papers."""
    from academic_hunter.interfaces.mcp.tools.related import find_related_papers

    mock_store = MagicMock()
    mock_store.query.return_value = [
        {
            "title": "Related Paper One",
            "semantic_relevance": 0.85,
            "year": 2024,
            "doi": "10.1000/one",
            "abstract_preview": "This paper discusses related concepts...",
        },
        {
            "title": "Related Paper Two",
            "semantic_relevance": 0.72,
            "year": 2023,
            "doi": "",
            "abstract_preview": "",
        },
    ]

    with patch("academic_hunter.interfaces.mcp.tools.related._get_vector_store") as m:
        m.return_value = mock_store
        result = await find_related_papers(mock_ctx, "blockchain payments")

    assert "Related Papers" in result
    assert "Related Paper One" in result
    assert "Related Paper Two" in result
    assert "10.1000/one" in result
    assert "85.0%" in result or "85%" in result


async def test_find_related_papers_truncates_query(mock_ctx):
    """Truncates long query in log message."""
    from academic_hunter.interfaces.mcp.tools.related import find_related_papers

    mock_store = MagicMock()
    mock_store.query.return_value = []

    with patch("academic_hunter.interfaces.mcp.tools.related._get_vector_store") as m:
        m.return_value = mock_store
        long_query = "A" * 200
        await find_related_papers(mock_ctx, long_query)
    mock_ctx.info.assert_called()
    # The first info call should contain truncated query
    first_call = mock_ctx.info.call_args_list[0]
    assert len(first_call[0][0]) < 150
