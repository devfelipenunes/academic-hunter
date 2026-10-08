"""Tests for find_novel_papers tool."""
from unittest.mock import MagicMock, patch

import pytest


async def test_find_novel_papers_no_vector_store(mock_ctx):
    """Returns message when vector store is unavailable."""
    from academic_hunter.interfaces.mcp.tools.novelty import find_novel_papers

    with patch("academic_hunter.interfaces.mcp.tools.novelty._get_vector_store") as m:
        m.return_value = None
        result = await find_novel_papers(mock_ctx)
    assert "Vector store not available" in result


async def test_find_novel_papers_too_few(mock_ctx):
    """Returns message when too few papers indexed."""
    from academic_hunter.interfaces.mcp.tools.novelty import find_novel_papers

    mock_store = MagicMock()
    mock_store.query.return_value = [{"title": "Only"} for _ in range(3)]

    with patch("academic_hunter.interfaces.mcp.tools.novelty._get_vector_store") as m:
        m.return_value = mock_store
        result = await find_novel_papers(mock_ctx)
    assert "Not enough papers" in result


async def test_find_novel_papers_import_error(mock_ctx):
    """Returns message when dependencies missing."""
    from academic_hunter.interfaces.mcp.tools.novelty import find_novel_papers

    mock_store = MagicMock()
    mock_store.query.return_value = [{"title": f"Paper {i}"} for i in range(20)]

    with patch("academic_hunter.interfaces.mcp.tools.novelty._get_vector_store") as m:
        m.return_value = mock_store
        with patch("sklearn.covariance.EllipticEnvelope") as m_env:
            m_env.side_effect = ImportError("No sklearn")
            result = await find_novel_papers(mock_ctx)
    assert "Required library" in result


async def test_find_novel_papers_no_outliers(mock_ctx):
    """Returns message when no outlier papers found."""
    from academic_hunter.interfaces.mcp.tools.novelty import find_novel_papers

    mock_store = MagicMock()
    mock_store.query.return_value = [{"title": f"Paper {i}"} for i in range(20)]

    with patch("academic_hunter.interfaces.mcp.tools.novelty._get_vector_store") as m:
        m.return_value = mock_store
        with patch("sklearn.covariance.EllipticEnvelope") as m_env:
            instance = m_env.return_value
            instance.fit_predict.return_value = [1] * 20
            instance.decision_function.return_value = [0.5] * 20
            with patch("sentence_transformers.SentenceTransformer") as m_st:
                mock_model = MagicMock()
                mock_model.encode.return_value = [[0.1] * 384 for _ in range(20)]
                m_st.return_value = mock_model
                result = await find_novel_papers(mock_ctx)
    assert "No outlier papers" in result


async def test_find_novel_papers_with_outliers(mock_ctx):
    """Returns formatted report when outliers found."""
    from academic_hunter.interfaces.mcp.tools.novelty import find_novel_papers

    papers = [
        {"title": f"Paper {i}", "year": 2024, "abstract_preview": "abstract..."}
        for i in range(20)
    ]
    mock_store = MagicMock()
    mock_store.query.return_value = papers

    with patch("academic_hunter.interfaces.mcp.tools.novelty._get_vector_store") as m:
        m.return_value = mock_store
        with patch("sklearn.covariance.EllipticEnvelope") as m_env:
            instance = m_env.return_value
            preds = [-1] * 3 + [1] * 17
            scores = [0.9, 0.8, 0.7] + [0.5] * 17
            instance.fit_predict.return_value = preds
            instance.decision_function.return_value = scores
            with patch("sentence_transformers.SentenceTransformer") as m_st:
                mock_model = MagicMock()
                mock_model.encode.return_value = [[0.1] * 384 for _ in range(20)]
                m_st.return_value = mock_model
                result = await find_novel_papers(mock_ctx)

    assert "Novel/Outlier Papers" in result
    assert "Paper 0" in result
    assert "Paper 1" in result
    assert "Paper 2" in result
    assert "20" in result or "analyzed" in result


async def test_find_novel_papers_general_exception(mock_ctx):
    """Propagates exception when vector store query fails."""
    from academic_hunter.interfaces.mcp.tools.novelty import find_novel_papers

    mock_store = MagicMock()
    mock_store.query.side_effect = Exception("Unexpected error")

    with patch("academic_hunter.interfaces.mcp.tools.novelty._get_vector_store") as m:
        m.return_value = mock_store
        with pytest.raises(Exception, match="Unexpected error"):
            await find_novel_papers(mock_ctx)


class _ListableStore:
    """A store that can list its collection, which is what makes it the corpus."""

    def __init__(self, papers):
        self.papers = papers
        self.listed = 0
        self.queried = []

    def all_papers(self, collection_name="papers"):
        self.listed += 1
        return self.papers

    def query(self, prompt, top_k=5, collection_name="papers", score_threshold=None):
        self.queried.append(prompt)
        return self.papers


async def test_outliers_are_found_in_the_corpus_not_near_a_phrase(mock_ctx):
    """`store.query("...")` answers a different question than "the corpus".

    The tool reported outliers of the neighbourhood around one hard-coded
    phrase, and called them the outliers of the indexed collection.
    """
    from academic_hunter.interfaces.mcp.tools.novelty import find_novel_papers

    store = _ListableStore([{"title": f"Paper {i}"} for i in range(20)])

    with patch("academic_hunter.interfaces.mcp.tools.novelty._get_vector_store") as m:
        m.return_value = store
        with patch("sklearn.covariance.EllipticEnvelope") as m_env:
            instance = m_env.return_value
            instance.fit_predict.return_value = [1] * 20
            instance.decision_function.return_value = [0.5] * 20
            with patch("sentence_transformers.SentenceTransformer") as m_st:
                model = MagicMock()
                model.encode.return_value = [[0.1] * 384 for _ in range(20)]
                m_st.return_value = model
                await find_novel_papers(mock_ctx)

    assert store.listed == 1, "the collection was never listed"
    assert store.queried == [], (
        f"the analysis described the neighbourhood of a phrase instead: {store.queried}"
    )
