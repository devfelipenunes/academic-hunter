"""Tests for visualization MCP tools (topic_evolution).

Uses mock_ctx from the MCP conftest and patches vector store,
SentenceTransformer, and BERTopic to avoid real API / model calls.
All patching uses the module-level names in visualization.py so that
``unittest.mock.patch`` can target them correctly.
"""

from unittest.mock import MagicMock, patch


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
        store.all_papers.return_value = mock_papers
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
        store.all_papers.return_value = store.query.return_value
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
            assert "academic-hunter[ml]" in result


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
        store.all_papers.return_value = mock_papers
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
                assert "2023" in result
                assert "Papers analyzed" in result


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


async def test_the_evolution_is_the_corpus_not_a_neighbourhood(mock_ctx):
    from academic_hunter.interfaces.mcp.tools.visualization import topic_evolution

    papers = [
        {"title": f"Paper {i}", "abstract_preview": f"A{i}", "year": 2020 + i % 3}
        for i in range(10)
    ]
    store = _ListableStore(papers)

    with patch(
        "academic_hunter.interfaces.mcp.tools.visualization._get_vector_store"
    ) as m_store, patch(
        "academic_hunter.interfaces.mcp.tools.visualization._load_bertopic"
    ) as m_bt, patch(
        "academic_hunter.interfaces.mcp.tools.visualization.get_sentence_transformer"
    ) as m_st:
        m_store.return_value = store
        topic_model = MagicMock()
        topic_model.fit_transform.return_value = ([0] * 10, None)
        topic_model.get_topic.return_value = [("deep", 0.5)]
        m_bt.return_value = MagicMock(return_value=topic_model)
        model = MagicMock()
        model.encode.return_value = [[0.1]] * 10
        m_st.return_value = model

        await topic_evolution(mock_ctx, top_k=10)

    assert store.listed == 1, "the collection was never listed"
    assert store.queried == [], (
        f"the evolution described the neighbourhood of a phrase: {store.queried}"
    )
