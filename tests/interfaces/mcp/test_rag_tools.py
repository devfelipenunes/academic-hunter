"""Tests for RAG MCP tools (semantic_search, index_papers, vector_store_stats, ask_papers).

Uses mock_ctx from conftest and patches ChromaVectorStore / AcademicHunter.
"""

import pytest
from unittest.mock import patch, MagicMock
from academic_hunter.interfaces.mcp.tools.rag import (
    semantic_search,
    index_papers,
    vector_store_stats,
    ask_papers,
)
from academic_hunter.interfaces.mcp.exceptions import MCPToolError


# ── semantic_search ───────────────────────────────────────────────────────────


async def test_semantic_search(mock_vector_store, mock_ctx):
    mock_vector_store.query.return_value = [
        {
            "title": "Paper A",
            "semantic_relevance": 0.95,
            "year": 2024,
            "source": "arXiv",
            "doi": "10.1234/a",
            "abstract_preview": "Important findings...",
        }
    ]

    result = await semantic_search("test query", ctx=mock_ctx, top_k=5, score_threshold=0.0)

    assert "Paper A" in result
    assert "95.00%" in result  # 0.95 formatted as percentage
    assert "arXiv" in result
    mock_vector_store.query.assert_called_once()
    mock_ctx.info.assert_called()


async def test_semantic_search_no_results(mock_vector_store, mock_ctx):
    mock_vector_store.query.return_value = []

    result = await semantic_search("unknown", ctx=mock_ctx)

    assert "No semantically relevant papers" in result
    mock_ctx.info.assert_called()


async def test_semantic_search_store_unavailable(mock_ctx):
    """When ChromaVectorStore can't be initialized, return meaningful error."""
    with patch(
        "academic_hunter.interfaces.mcp.tools.rag.ChromaVectorStore"
    ) as m:
        m.side_effect = RuntimeError("ChromaDB not installed")
        result = await semantic_search("test", ctx=mock_ctx)
        assert "Error" in result
        assert "vector store" in result.lower()


# ── index_papers ──────────────────────────────────────────────────────────────


async def test_index_papers(mock_hunter_rag, mock_vector_store, mock_ctx):
    mock_hunter_rag.consolidated_results = {"paper1": MagicMock(), "paper2": MagicMock()}

    result = await index_papers(mock_ctx)

    assert "Successfully indexed" in result
    assert "2 papers" in result
    mock_vector_store.index_papers.assert_called_once()
    mock_ctx.info.assert_called()


async def test_index_papers_no_results(mock_hunter_rag, mock_ctx):
    mock_hunter_rag.consolidated_results = {}

    result = await index_papers(mock_ctx)

    assert "No papers found" in result


async def test_index_papers_failure(mock_hunter_rag, mock_vector_store, mock_ctx):
    mock_hunter_rag.consolidated_results = {"paper1": MagicMock()}
    mock_vector_store.index_papers.return_value = False

    result = await index_papers(mock_ctx)

    assert "Failed to index" in result
    mock_ctx.error.assert_called()


# ── vector_store_stats ─────────────────────────────────────────────────────────


async def test_vector_store_stats_populated(mock_vector_store, mock_ctx):
    mock_vector_store.collection_stats.return_value = {"count": 42}
    mock_vector_store.list_collections.return_value = ["papers"]

    result = await vector_store_stats(mock_ctx)

    assert "42" in result
    assert "papers" in result
    assert "ready" in result.lower()
    mock_ctx.info.assert_called()


async def test_vector_store_stats_empty(mock_vector_store, mock_ctx):
    mock_vector_store.collection_stats.return_value = {"count": 0}

    result = await vector_store_stats(mock_ctx)

    assert "No papers indexed" in result


async def test_vector_store_stats_unavailable(mock_ctx):
    with patch(
        "academic_hunter.interfaces.mcp.tools.rag.ChromaVectorStore"
    ) as m:
        m.side_effect = RuntimeError("ChromaDB not installed")
        result = await vector_store_stats(mock_ctx)
        assert "not available" in result.lower()


# ── ask_papers ────────────────────────────────────────────────────────────────


async def test_ask_papers(mock_vector_store, mock_ctx):
    mock_vector_store.query.return_value = [
        {
            "title": "Relevant Paper",
            "semantic_relevance": 0.92,
            "year": 2024,
            "abstract_preview": "This paper discusses important concepts.",
        }
    ]

    result = await ask_papers("What is the main finding?", ctx=mock_ctx, top_k=5)

    assert "Relevant Paper" in result
    assert "92.00%" in result
    assert "What is the main finding?" in result
    mock_vector_store.query.assert_called_once()
    mock_ctx.info.assert_called()


async def test_ask_papers_no_results(mock_vector_store, mock_ctx):
    mock_vector_store.query.return_value = []

    result = await ask_papers("unknown", ctx=mock_ctx)

    assert "No relevant papers found" in result
