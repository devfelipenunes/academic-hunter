"""Tests for visualization MCP tools (visualize_landscape, topic_evolution).

Uses mock_ctx from the MCP conftest and patches vector store, UMAP,
SentenceTransformer, and BERTopic to avoid real API / model calls.
All patching uses the module-level names in visualization.py so that
``unittest.mock.patch`` can target them correctly.
"""

import json
from unittest.mock import MagicMock, patch

import numpy as np

# ── visualize_landscape tests ──────────────────────────────────────────────────


async def test_visualize_landscape(mock_ctx):
    """Returns JSON with 2D coordinates and paper metadata."""
    mock_papers = [
        {"title": f"Paper {i}", "abstract_preview": f"Abstract {i}"}
        for i in range(10)
    ]
    mock_embeddings = np.array([[float(i), float(i)] for i in range(10)])

    with patch(
        "academic_hunter.interfaces.mcp.tools.visualization._get_vector_store"
    ) as m_store:
        store = MagicMock()
        store.query.return_value = mock_papers
        m_store.return_value = store

        m_umap = MagicMock()
        m_umap.UMAP.return_value.fit_transform.return_value = mock_embeddings
        with patch(
            "academic_hunter.interfaces.mcp.tools.visualization._load_umap",
            return_value=m_umap,
        ):

            with patch(
                "academic_hunter.interfaces.mcp.tools.visualization.get_sentence_transformer"
            ) as m_st:
                model = MagicMock()
                model.encode.return_value = mock_embeddings
                m_st.return_value = model

                from academic_hunter.interfaces.mcp.tools.visualization import (
                    visualize_landscape,
                )

                result = await visualize_landscape(mock_ctx, top_k=10)
                data = json.loads(result)
                assert "papers" in data
                assert len(data["papers"]) == 10
                assert "shape" in data
                assert data["papers"][0]["x"] == 0.0
                assert data["papers"][0]["y"] == 0.0
                mock_ctx.info.assert_called()


async def test_visualize_landscape_no_store(mock_ctx):
    """Graceful when vector store is unavailable."""
    with patch(
        "academic_hunter.interfaces.mcp.tools.visualization._get_vector_store",
        return_value=None,
    ):
        from academic_hunter.interfaces.mcp.tools.visualization import (
            visualize_landscape,
        )

        result = await visualize_landscape(mock_ctx)
        assert "not available" in result.lower()


async def test_visualize_landscape_few_papers(mock_ctx):
    """Graceful with too few papers (less than 5)."""
    with patch(
        "academic_hunter.interfaces.mcp.tools.visualization._get_vector_store"
    ) as m_store:
        store = MagicMock()
        store.query.return_value = [{"title": "Only one"}]
        m_store.return_value = store

        from academic_hunter.interfaces.mcp.tools.visualization import (
            visualize_landscape,
        )

        result = await visualize_landscape(mock_ctx)
        assert "Not enough papers" in result


async def test_visualize_landscape_empty_results(mock_ctx):
    """Graceful when vector store returns no results."""
    with patch(
        "academic_hunter.interfaces.mcp.tools.visualization._get_vector_store"
    ) as m_store:
        store = MagicMock()
        store.query.return_value = []
        m_store.return_value = store

        from academic_hunter.interfaces.mcp.tools.visualization import (
            visualize_landscape,
        )

        result = await visualize_landscape(mock_ctx)
        assert "Not enough papers" in result


async def test_visualize_landscape_import_error(mock_ctx):
    """Graceful when SentenceTransformer is not installed."""
    with patch(
        "academic_hunter.interfaces.mcp.tools.visualization._get_vector_store"
    ) as m_store:
        store = MagicMock()
        store.query.return_value = [{"title": f"P{i}"} for i in range(10)]
        m_store.return_value = store

        with patch(
            "academic_hunter.interfaces.mcp.tools.visualization._load_umap",
            return_value=MagicMock(),
        ):
            with patch(
                "academic_hunter.interfaces.mcp.tools.visualization.get_sentence_transformer",
                MagicMock(return_value=None),
            ):
                from academic_hunter.interfaces.mcp.tools.visualization import (
                    visualize_landscape,
                )

                result = await visualize_landscape(mock_ctx, top_k=10)
                assert "not installed" in result.lower() or "Required library" in result


# ── topic_evolution tests ──────────────────────────────────────────────────────


async def test_topic_evolution(mock_ctx):
    """Returns evolution data grouped by year."""
    mock_papers = [
        {"title": "Deep Learning", "abstract_preview": "Neural networks", "year": 2022},
        {"title": "Transformers", "abstract_preview": "Attention mechanism", "year": 2023},
        {"title": "LLM Reasoning", "abstract_preview": "Language models", "year": 2024},
        {"title": "GANs for Vision", "abstract_preview": "Generative models", "year": 2023},
        {"title": "Reinforcement Learning", "abstract_preview": "Policy gradients", "year": 2022},
    ]

    with patch(
        "academic_hunter.interfaces.mcp.tools.visualization._get_vector_store"
    ) as m_store:
        store = MagicMock()
        store.query.return_value = mock_papers
        m_store.return_value = store

        model = MagicMock()
        model.fit_transform.return_value = ([0, 1, 2, 1, 0], None)
        model.get_topic.return_value = [("deep", 0.5), ("learning", 0.3)]
        with patch(
            "academic_hunter.interfaces.mcp.tools.visualization._load_bertopic",
            return_value=MagicMock(return_value=model),
        ):

            with patch(
                "academic_hunter.interfaces.mcp.tools.visualization.get_sentence_transformer"
            ) as m_st:
                st_model = MagicMock()
                st_model.encode.return_value = [[0.1], [0.2], [0.3], [0.4], [0.5]]
                m_st.return_value = st_model

                from academic_hunter.interfaces.mcp.tools.visualization import (
                    topic_evolution,
                )

                result = await topic_evolution(mock_ctx, top_k=10)
                assert "Evolution" in result or "2022" in result or "2023" in result
                mock_ctx.info.assert_called()


async def test_topic_evolution_no_store(mock_ctx):
    """Graceful when vector store is unavailable."""
    with patch(
        "academic_hunter.interfaces.mcp.tools.visualization._get_vector_store",
        return_value=None,
    ):
        from academic_hunter.interfaces.mcp.tools.visualization import (
            topic_evolution,
        )

        result = await topic_evolution(mock_ctx)
        assert "not available" in result.lower()


async def test_topic_evolution_few_papers(mock_ctx):
    """Graceful with too few papers."""
    with patch(
        "academic_hunter.interfaces.mcp.tools.visualization._get_vector_store"
    ) as m_store:
        store = MagicMock()
        store.query.return_value = [{"title": "Only one"}]
        m_store.return_value = store

        from academic_hunter.interfaces.mcp.tools.visualization import (
            topic_evolution,
        )

        result = await topic_evolution(mock_ctx)
        assert "Not enough papers" in result


async def test_topic_evolution_bertopic_not_installed(mock_ctx):
    """Graceful when BERTopic is not installed."""
    with patch(
        "academic_hunter.interfaces.mcp.tools.visualization._get_vector_store"
    ) as m_store:
        store = MagicMock()
        store.query.return_value = [
            {"title": f"P{i}", "abstract_preview": f"A{i}", "year": 2022}
            for i in range(10)
        ]
        m_store.return_value = store

        with patch(
            "academic_hunter.interfaces.mcp.tools.visualization._load_bertopic",
            side_effect=ImportError("no bertopic"),
        ):
            from academic_hunter.interfaces.mcp.tools.visualization import (
                topic_evolution,
            )

            result = await topic_evolution(mock_ctx, top_k=10)
            assert "BERTopic not installed" in result


async def test_topic_evolution_no_year(mock_ctx):
    """Handles papers without a year gracefully."""
    mock_papers = [
        {"title": "No date paper", "abstract_preview": "Abstract", "year": None},
        {"title": "Another", "abstract_preview": "More text", "year": 2023},
        {"title": "Paper Three", "abstract_preview": "Content", "year": 2023},
        {"title": "Paper Four", "abstract_preview": "More", "year": 2022},
        {"title": "Paper Five", "abstract_preview": "Extra", "year": 2023},
    ]

    with patch(
        "academic_hunter.interfaces.mcp.tools.visualization._get_vector_store"
    ) as m_store:
        store = MagicMock()
        store.query.return_value = mock_papers
        m_store.return_value = store

        model = MagicMock()
        model.fit_transform.return_value = ([0, 1, 2, 3, 0], None)
        model.get_topic.return_value = [("test", 0.5)]
        with patch(
            "academic_hunter.interfaces.mcp.tools.visualization._load_bertopic",
            return_value=MagicMock(return_value=model),
        ):

            with patch(
                "academic_hunter.interfaces.mcp.tools.visualization.get_sentence_transformer"
            ) as m_st:
                st_model = MagicMock()
                st_model.encode.return_value = [[0.1], [0.2], [0.3], [0.4], [0.5]]
                m_st.return_value = st_model

                from academic_hunter.interfaces.mcp.tools.visualization import (
                    topic_evolution,
                )

                result = await topic_evolution(mock_ctx, top_k=10)
                # The None-year paper should be excluded (year = 0), so only 2023 appears
                assert "2023" in result
                # Despite the excluded paper, the headline count includes all docs
                assert "Papers analyzed" in result
