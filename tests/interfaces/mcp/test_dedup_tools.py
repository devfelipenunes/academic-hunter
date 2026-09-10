"""Tests for semantic dedup tool."""

from unittest.mock import MagicMock, patch

import pytest

from academic_hunter.interfaces.mcp.tools.dedup import semantic_dedup


async def test_semantic_dedup(mock_ctx):
    """Returns duplicate groups from embeddings."""
    mock_papers = [
        {"title": "Deep Learning for NLP", "abstract_preview": "Neural networks for text"},
        {"title": "Deep Learning in NLP", "abstract_preview": "Neural networks for language"},
        {"title": "Quantum Computing", "abstract_preview": "Quantum bits and gates"},
    ]
    mock_embeddings = [[1.0, 0.0], [0.99, 0.01], [0.0, 1.0]]

    with patch("academic_hunter.interfaces.mcp.tools.dedup._get_vector_store") as m_get:
        store = MagicMock()
        store.query.return_value = mock_papers
        m_get.return_value = store
        with patch("academic_hunter.interfaces.mcp.tools.dedup.get_sentence_transformer") as m_st:
            model = MagicMock()
            model.encode.return_value = mock_embeddings
            m_st.return_value = model
            result = await semantic_dedup(mock_ctx, threshold=0.8, min_group_size=2)
            assert "Duplicate" in result or "dedup" in result.lower()
            mock_ctx.info.assert_called()
            # The embeddings must actually have been computed; without this the
            # test still passes when the model is absent and the tool bails out.
            model.encode.assert_called_once()


async def test_semantic_dedup_no_store(mock_ctx):
    """Graceful when no store."""
    with patch(
        "academic_hunter.interfaces.mcp.tools.dedup._get_vector_store",
        return_value=None,
    ):
        result = await semantic_dedup(mock_ctx)
        assert "not available" in result


async def test_semantic_dedup_few_papers(mock_ctx):
    """Graceful with too few papers."""
    with patch("academic_hunter.interfaces.mcp.tools.dedup._get_vector_store") as m_get:
        store = MagicMock()
        store.query.return_value = [{"title": "Only one paper"}]
        m_get.return_value = store
        result = await semantic_dedup(mock_ctx)
        assert "Not enough papers" in result
