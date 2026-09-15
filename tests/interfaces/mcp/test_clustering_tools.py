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

        topic_model = MagicMock()
        # Simulate 2 topics + outliers
        topic_model.fit_transform.return_value = ([0, 1, -1], None)
        topic_model.get_topic_info.return_value = MagicMock()
        topic_model.get_topic.return_value = [("deep", 0.5), ("learning", 0.3)]

        with patch(
            "academic_hunter.interfaces.mcp.tools.clustering._load_bertopic",
            return_value=MagicMock(return_value=topic_model),
        ):
            result = await cluster_papers(mock_ctx, top_k=100)

            assert "Topic Clusters" in result
            assert "deep" in result.lower()
            mock_ctx.info.assert_called()


async def test_cluster_papers_without_bertopic_says_how_to_install_it(mock_ctx):
    """BERTopic is optional and imported on use, so absence is a message, not a crash."""
    with patch("academic_hunter.interfaces.mcp.tools.clustering._get_vector_store") as m_store:
        store = MagicMock()
        store.query.return_value = [{"title": f"Paper {i}"} for i in range(5)]
        m_store.return_value = store

        with patch(
            "academic_hunter.interfaces.mcp.tools.clustering._load_bertopic",
            side_effect=ImportError("no bertopic"),
        ):
            result = await cluster_papers(mock_ctx, top_k=100)

    assert "pip install bertopic" in result
    mock_ctx.error.assert_called()


def test_the_server_does_not_import_bertopic_at_startup():
    """The measured reason: it was 16 s of the MCP server's startup.

    Importing the tool module must not pull the ML stack in; if it does, every
    client pays for a tool most sessions never call.
    """
    import subprocess
    import sys

    code = (
        "import sys; import academic_hunter.interfaces.mcp.tools.clustering;"
        "print('bertopic' in sys.modules)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)

    assert out.stdout.strip() == "False", out.stderr[-500:]


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
