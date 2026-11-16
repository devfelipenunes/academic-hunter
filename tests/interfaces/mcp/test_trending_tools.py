"""Tests for trending_topics tool."""
from unittest.mock import MagicMock, patch


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
    mock_store.all_papers.return_value = []

    with patch("academic_hunter.interfaces.mcp.tools.trending._get_vector_store") as m:
        m.return_value = mock_store
        result = await trending_topics(mock_ctx)
    assert "No indexed papers" in result or "No trending" in result


async def test_trending_topics_no_bigrams_meet_threshold(mock_ctx):
    """Returns message when no bigrams meet min_papers threshold."""
    from academic_hunter.interfaces.mcp.tools.trending import trending_topics

    mock_store = MagicMock()
    mock_store.query.return_value = [
        {"title": "Deep Learning Methods"},
        {"title": "Deep Learning Advances"},
    ]
    mock_store.all_papers.return_value = mock_store.query.return_value

    with patch("academic_hunter.interfaces.mcp.tools.trending._get_vector_store") as m:
        m.return_value = mock_store
        result = await trending_topics(mock_ctx, min_papers=3)
    assert "No topic reached the minimum" in result, result
    assert "Index papers first" not in result, result


async def test_an_indexed_corpus_is_never_told_to_index_papers(mock_ctx):
    """An indexed corpus below the threshold must not claim nothing is indexed.

    Both branches returned the same sentence, so a caller with papers indexed was
    told to index papers -- and the tool that says so is one an agent will go on
    to distrust. The empty case keeps its message; the threshold case has to say
    what it counted instead.
    """
    from academic_hunter.interfaces.mcp.tools.trending import trending_topics

    papers = [{"title": "Deep Learning Methods"}, {"title": "Deep Learning Advances"}]

    store = MagicMock()
    store.query.return_value = papers
    store.all_papers.return_value = papers
    with patch("academic_hunter.interfaces.mcp.tools.trending._get_vector_store") as m:
        m.return_value = store
        below = await trending_topics(mock_ctx, min_papers=3)

    assert "Index papers first" not in below, below
    assert "2" in below, f"the number of papers analyzed is missing: {below}"
    assert "3" in below, f"the threshold it failed to reach is missing: {below}"

    empty = MagicMock()
    empty.query.return_value = []
    empty.all_papers.return_value = []
    with patch("academic_hunter.interfaces.mcp.tools.trending._get_vector_store") as m:
        m.return_value = empty
        nothing = await trending_topics(mock_ctx, min_papers=3)

    assert "Index papers first" in nothing, nothing


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
    mock_store.query.return_value = mock_papers
    mock_store.all_papers.return_value = mock_papers

    with patch("academic_hunter.interfaces.mcp.tools.trending._get_vector_store") as m:
        m.return_value = mock_store
        result = await trending_topics(mock_ctx, min_papers=2)

    assert "Trending Research Topics" in result
    assert "Deep Learning" in result
    assert "Blockchain Scalability" in result
    assert "6" in result


async def test_trending_topics_empty_title_skipped(mock_ctx):
    """Skips papers with empty titles.

    The surviving title has to be one that actually yields a bigram: "paper" and
    "title" are both stopwords, so a corpus of "Single Paper Title" produces none
    and the test would pass through the below-threshold branch instead of the one
    it names.
    """
    from academic_hunter.interfaces.mcp.tools.trending import trending_topics

    mock_store = MagicMock()
    mock_store.query.return_value = [
        {"title": ""},
        {"title": "Blockchain Scalability Solutions"},
    ]
    mock_store.all_papers.return_value = mock_store.query.return_value

    with patch("academic_hunter.interfaces.mcp.tools.trending._get_vector_store") as m:
        m.return_value = mock_store
        result = await trending_topics(mock_ctx, min_papers=1)
    assert "# Trending Research Topics" in result, result
    assert "Blockchain Scalability" in result, result


async def test_extract_bigrams_basic():
    """Extracts meaningful bigrams from a title."""
    from academic_hunter.interfaces.mcp.tools.trending import _extract_bigrams

    stopwords = {"the", "a", "an", "of", "for", "in", "and"}
    result = _extract_bigrams("Deep Learning for NLP", stopwords)

    assert "deep learning" in result
    assert "learning for" not in result
    assert "for nlp" not in result
    assert "learning nlp" not in result


def test_extract_bigrams_short_words():
    """Filters out short words (<= 2 chars)."""
    from academic_hunter.interfaces.mcp.tools.trending import _extract_bigrams

    stopwords = set()
    result = _extract_bigrams("AI for ML is cool stuff", stopwords)

    assert "ai for" not in result
    assert "ai" not in result


def test_extract_bigrams_empty_title():
    """Returns empty list for blank title."""
    from academic_hunter.interfaces.mcp.tools.trending import _extract_bigrams

    assert _extract_bigrams("", set()) == []
    assert _extract_bigrams("   ", set()) == []
