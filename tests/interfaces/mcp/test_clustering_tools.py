"""Tests for clustering MCP tools (cluster_papers)."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from academic_hunter.interfaces.mcp.tools.clustering import cluster_papers


async def test_cluster_papers_success(mock_ctx):
    """Returns topic clusters from indexed papers."""
    mock_results = [
        {"title": "Deep Learning for NLP", "abstract": "A paper about deep learning..."},
        {"title": "Transformers in Vision", "abstract": "Using transformers for images..."},
        {"title": "CNN for Classification", "abstract": "Convolutional neural networks..."},
    ]

    with patch("academic_hunter.interfaces.mcp.tools.clustering._get_vector_store") as m_store:
        store = MagicMock()
        store.query.return_value = mock_results
        m_store.return_value = store

        with patch("academic_hunter.interfaces.mcp.tools.clustering.BERTopic") as m_bt:
            topic_model = MagicMock()
            # Simulate 2 topics + outliers
            topic_model.fit_transform.return_value = ([0, 1, -1], None)
            topic_model.get_topic_info.return_value = MagicMock()
            topic_model.get_topic.return_value = [("deep", 0.5), ("learning", 0.3)]
            m_bt.return_value = topic_model

            result = await cluster_papers(mock_ctx, top_k=100)

            assert "Topic Clusters" in result
            assert "deep" in result.lower()
            mock_ctx.info.assert_called()


async def test_cluster_papers_no_store(mock_ctx):
    """Graceful handling when vector store is unavailable."""
    with patch("academic_hunter.interfaces.mcp.tools.clustering._get_vector_store") as m_store:
        m_store.return_value = None

        result = await cluster_papers(mock_ctx)
        assert "Vector store not available" in result


async def test_cluster_papers_no_results(mock_ctx):
    """Graceful handling when no papers are indexed."""
    with patch("academic_hunter.interfaces.mcp.tools.clustering._get_vector_store") as m_store:
        store = MagicMock()
        store.query.return_value = []
        m_store.return_value = store

        result = await cluster_papers(mock_ctx)
        assert "No papers found" in result
