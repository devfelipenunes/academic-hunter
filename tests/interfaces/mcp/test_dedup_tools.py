"""Tests for semantic dedup tool."""

from unittest.mock import MagicMock, patch

import pytest

from academic_hunter.interfaces.mcp.exceptions import VectorStoreError
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
        store.all_papers.return_value = mock_papers
        m_get.return_value = store
        with patch("academic_hunter.interfaces.mcp.tools.dedup.get_sentence_transformer") as m_st:
            model = MagicMock()
            model.encode.return_value = mock_embeddings
            m_st.return_value = model
            result = await semantic_dedup(mock_ctx, threshold=0.8, min_group_size=2)
            assert "Duplicate" in result or "dedup" in result.lower()
            mock_ctx.info.assert_called()
            model.encode.assert_called_once()


async def test_semantic_dedup_no_store(mock_ctx):
    """A missing store is an error, and it is raised rather than described.

    Returning the sentence as ordinary tool output made the failure look like
    a successful call: FastMCP only marks `isError` for a raised exception, so
    the client read "Error: ..." as the tool's answer.
    """
    with patch(
        "academic_hunter.interfaces.mcp.tools.dedup._get_vector_store",
        return_value=None,
    ):
        with pytest.raises(VectorStoreError, match="not available"):
            await semantic_dedup(mock_ctx)


async def test_semantic_dedup_few_papers(mock_ctx):
    """Graceful with too few papers."""
    with patch("academic_hunter.interfaces.mcp.tools.dedup._get_vector_store") as m_get:
        store = MagicMock()
        store.query.return_value = [{"title": "Only one paper"}]
        m_get.return_value = store
        result = await semantic_dedup(mock_ctx)
        assert "Not enough papers" in result


async def test_a_rejected_seed_does_not_swallow_the_group_behind_it(mock_ctx):
    """A seed that forms no group must not consume its neighbours.

    ``visited.add(j)`` ran for every pair above the threshold, while the seed
    itself was only marked once its group was kept. Papers 0 and 1 are close
    enough to pair, but two is below ``min_group_size``, so the seed was
    discarded — after having already claimed 1. Paper 1 was then skipped as
    visited, and the genuine four-paper group behind it never formed: the run
    reported zero duplicates over a corpus that had four.
    """
    papers = [
        {"title": f"Paper {i}", "abstract_preview": f"a{i}"} for i in range(5)
    ]
    embeddings = [
        [1.0, 0.0],
        [0.91, 0.4146],
        [0.88, 0.4750],
        [0.88, 0.4750],
        [0.88, 0.4750],
    ]

    with patch("academic_hunter.interfaces.mcp.tools.dedup._get_vector_store") as m_get:
        store = MagicMock()
        store.query.return_value = papers
        m_get.return_value = store
        with patch(
            "academic_hunter.interfaces.mcp.tools.dedup.get_sentence_transformer"
        ) as m_st:
            model = MagicMock()
            model.encode.return_value = embeddings
            m_st.return_value = model
            result = await semantic_dedup(
                mock_ctx, threshold=0.9, min_group_size=4
            )

    assert "**Duplicate groups:** 1" in result, result
    for i in (1, 2, 3, 4):
        assert f"Paper {i}" in result, f"Paper {i} was left out of its own group"
    assert "Paper 0" not in result, "the rejected seed was reported as a duplicate"
