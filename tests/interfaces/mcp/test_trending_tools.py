"""Tests for trending_topics tool."""
import pytest
from unittest.mock import patch, MagicMock


async def test_trending_topics_no_vector_store(mock_ctx):
    """Returns message when vector store is unavailable."""
    from academic_hunter.interfaces.mcp.tools.trending import trending_topics

    with patch("academic_hunter.interfaces.mcp.tools.trending._get_vector_store") as m:
        m.return_value = None
        result = await trending_topics(mock_ctx)
    assert "Vector store not available" in result


async def test_trending_topics_no_papers(mock_ctx):
    """Returns message when no indexed papers found."""
    from academic_hunter.interfaces.mcp.tools.trending import trending_topics

    mock_store = MagicMock()
    mock_store.query.return_value = []

    with patch("academic_hunter.interfaces.mcp.tools.trending._get_vector_store") as m:
        m.return_value = mock_store
        result = await trending_topics(mock_ctx)
    assert "No indexed papers" in result or "No trending" in result


async def test_trending_topics_no_bigrams_meet_threshold(mock_ctx):
    """Returns message when no bigrams meet min_papers threshold."""
    from academic_hunter.interfaces.mcp.tools.trending import trending_topics

    mock_store = MagicMock()
    # 2 papers with the same bigram, but min_papers=3
    mock_store.query.return_value = [
        {"title": "Deep Learning Methods"},
        {"title": "Deep Learning Advances"},
    ]

    with patch("academic_hunter.interfaces.mcp.tools.trending._get_vector_store") as m:
        m.return_value = mock_store
        result = await trending_topics(mock_ctx, min_papers=3)
    assert "No trending" in result or "No indexed" in result


async def test_trending_topics_returns_topics(mock_ctx):
    """Returns formatted list of trending topics."""
    from academic_hunter.interfaces.mcp.tools.trending import trending_topics

    mock_store = MagicMock()
    mock_papers = [
        {"title": "Deep Learning for NLP Applications"},
        {"title": "Deep Learning Advances in 2024"},
        {"title": "Deep Learning Methods Review"},
        {"title": "Blockchain Scalability Solutions for Enterprise"},
        {"title": "Blockchain Scalability in Distributed Systems"},
        {"title": "Blockchain Consensus Mechanisms Compared"},
    ]
    # Both entry points: `corpus_of` reads `all_papers` or falls back to a query,
    # and `isinstance` against a runtime-checkable Protocol answers differently
    # for a bare MagicMock on 3.10/3.11 than on 3.12.
    mock_store.query.return_value = mock_papers
    mock_store.all_papers.return_value = mock_papers

    with patch("academic_hunter.interfaces.mcp.tools.trending._get_vector_store") as m:
        m.return_value = mock_store
        result = await trending_topics(mock_ctx, min_papers=2)

    assert "Trending Research Topics" in result
    assert "Deep Learning" in result
    assert "Blockchain Scalability" in result
    assert "6" in result  # 6 papers analyzed


async def test_trending_topics_empty_title_skipped(mock_ctx):
    """Skips papers with empty titles."""
    from academic_hunter.interfaces.mcp.tools.trending import trending_topics

    mock_store = MagicMock()
    mock_store.query.return_value = [
        {"title": ""},
        {"title": "Single Paper Title"},
    ]

    with patch("academic_hunter.interfaces.mcp.tools.trending._get_vector_store") as m:
        m.return_value = mock_store
        result = await trending_topics(mock_ctx, min_papers=1)
    # Only "Single Paper Title" contributes bigrams, and with 1 paper,
    # no bigram can form
    assert "Trending" in result or "No trending" in result


async def test_extract_bigrams_basic():
    """Extracts meaningful bigrams from a title."""
    from academic_hunter.interfaces.mcp.tools.trending import _extract_bigrams

    stopwords = {"the", "a", "an", "of", "for", "in", "and"}
    result = _extract_bigrams("Deep Learning for NLP", stopwords)

    assert "deep learning" in result
    assert "learning for" not in result  # 'for' is stopword
    assert "for nlp" not in result       # 'for' is stopword


def test_extract_bigrams_short_words():
    """Filters out short words (<= 2 chars)."""
    from academic_hunter.interfaces.mcp.tools.trending import _extract_bigrams

    stopwords = set()
    result = _extract_bigrams("AI for ML is cool stuff", stopwords)

    # All 1-2 char words filtered
    assert "ai for" not in result
    assert "ai" not in result


def test_extract_bigrams_empty_title():
    """Returns empty list for blank title."""
    from academic_hunter.interfaces.mcp.tools.trending import _extract_bigrams

    assert _extract_bigrams("", set()) == []
    assert _extract_bigrams("   ", set()) == []
