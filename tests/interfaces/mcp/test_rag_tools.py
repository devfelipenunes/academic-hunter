"""Tests for RAG MCP tools (semantic_search, index_papers, vector_store_stats).

Uses mock_ctx from conftest and patches ChromaVectorStore / AcademicHunter.
"""

from unittest.mock import MagicMock, patch

import pytest

from academic_hunter.interfaces.mcp.exceptions import VectorStoreError
from academic_hunter.interfaces.mcp.tools.rag import (
    answer_question,
    delete_collection,
    index_papers,
    semantic_search,
    vector_store_stats,
)


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
    assert "95.00%" in result
    assert "arXiv" in result
    mock_vector_store.query.assert_called_once()
    mock_ctx.info.assert_called()


async def test_semantic_search_no_results(mock_vector_store, mock_ctx):
    mock_vector_store.query.return_value = []

    result = await semantic_search("unknown", ctx=mock_ctx)

    assert "No semantically relevant papers" in result
    mock_ctx.info.assert_called()


async def test_semantic_search_store_unavailable(mock_ctx):
    """When vector store can't be initialized, return meaningful error."""
    with patch(
        "academic_hunter.interfaces.mcp.tools.rag._get_vector_store",
        return_value=None,
    ):
        with pytest.raises(VectorStoreError, match="[Vv]ector store"):
            await semantic_search("test", ctx=mock_ctx)


async def test_index_papers(mock_hunter_rag, mock_vector_store, mock_ctx):
    mock_hunter_rag.consolidated_results = {"paper1": MagicMock(), "paper2": MagicMock()}

    result = await index_papers(mock_ctx)

    assert "Successfully indexed" in result
    assert "2 papers" in result
    mock_vector_store.index_papers.assert_called_once()
    mock_ctx.info.assert_called()


async def test_index_papers_no_results(mock_hunter_rag, mock_ctx):
    """Nothing in memory and nothing on disk.

    The disk read is patched away: this test is about the message, and the real
    `results/` directory has CSVs from previous runs.
    """
    mock_hunter_rag.consolidated_results = {}

    with patch(
        "academic_hunter.interfaces.mcp.tools.rag._load_latest_papers",
        return_value=[],
    ):
        result = await index_papers(mock_ctx)

    assert "No papers found" in result


async def test_index_papers_failure(mock_hunter_rag, mock_vector_store, mock_ctx):
    mock_hunter_rag.consolidated_results = {"paper1": MagicMock()}
    mock_vector_store.index_papers.return_value = False

    with pytest.raises(VectorStoreError, match="Failed to index"):
        await index_papers(mock_ctx)
    mock_ctx.error.assert_called()


async def test_vector_store_stats_populated(mock_vector_store, mock_ctx):
    mock_vector_store.collection_stats.return_value = {"count": 42}
    mock_vector_store.list_collections.return_value = ["papers"]

    result = await vector_store_stats(mock_ctx)

    assert "42" in result
    assert "papers" in result
    assert "this review" in result
    mock_ctx.info.assert_called()


async def test_vector_store_stats_empty(mock_vector_store, mock_ctx):
    mock_vector_store.collection_stats.return_value = {"count": 0}
    mock_vector_store.list_collections.return_value = ["papers"]

    result = await vector_store_stats(mock_ctx)

    assert "`papers` is empty" in result
    assert "index_papers" in result


async def test_a_review_whose_collection_is_missing_is_told_apart_from_an_empty_one(
    mock_vector_store, mock_ctx
):
    """The store has papers, but not for this review.

    With one collection per review, "0" is ambiguous: it can mean this review has
    not been indexed, or that something else is in the store. The two need
    different fixes and must not read the same.
    """
    mock_vector_store.list_collections.return_value = ["papers"]
    mock_vector_store.collection_stats.return_value = {"count": 1040}
    mock_vector_store.default_collection = "review_blockchain_ia"

    result = await vector_store_stats(mock_ctx)

    assert "`review_blockchain_ia` does not exist yet" in result
    assert "is empty" not in result
    assert "**Papers in it:** 0" in result


async def test_vector_store_stats_names_the_collection_the_review_reads(
    mock_vector_store, mock_ctx
):
    """One collection per review, and the reply has to say which one is live.

    Two reviews leave two collections side by side. Without the marker, a count
    of 0 for this review and a count of 0 for a missing one read the same.
    """
    mock_vector_store.list_collections.return_value = ["review_blockchain_ia", "papers"]
    mock_vector_store.collection_stats.side_effect = lambda name=None: {
        "review_blockchain_ia": {"count": 97},
        "papers": {"count": 1040},
    }[name]
    mock_vector_store.default_collection = "review_blockchain_ia"

    result = await vector_store_stats(mock_ctx)

    assert "**Collection in use:** `review_blockchain_ia`" in result
    assert "**Papers in it:** 97" in result
    assert "**Papers across all collections:** 1137" in result
    assert "- `review_blockchain_ia`: 97 papers  ← this review" in result
    assert "- `papers`: 1040 papers" in result
    assert "1040 papers  ←" not in result


async def test_vector_store_stats_empty_store(mock_vector_store, mock_ctx):
    mock_vector_store.list_collections.return_value = []

    result = await vector_store_stats(mock_ctx)

    assert "No collections yet" in result


async def test_vector_store_stats_unavailable(mock_ctx):
    with patch(
        "academic_hunter.interfaces.mcp.tools.rag._get_vector_store",
        return_value=None,
    ):
        result = await vector_store_stats(mock_ctx)
        assert "not available" in result.lower()


async def test_deleting_names_what_goes_before_it_goes(mock_vector_store, mock_ctx):
    """Nothing is removed without confirm, and the reply says what would be."""
    mock_vector_store.list_collections.return_value = ["papers"]
    mock_vector_store.collection_stats.return_value = {"count": 1040}

    result = await delete_collection("papers", ctx=mock_ctx)

    assert "1040 papers and nothing was deleted" in result
    assert "confirm=true" in result
    mock_vector_store.delete_collection.assert_not_called()


async def test_confirmed_deletion_removes_the_collection(mock_vector_store, mock_ctx):
    mock_vector_store.list_collections.return_value = ["papers"]
    mock_vector_store.collection_stats.return_value = {"count": 1040}
    mock_vector_store.delete_collection.return_value = True

    result = await delete_collection("papers", confirm=True, ctx=mock_ctx)

    assert "Deleted `papers` and its 1040 papers" in result
    mock_vector_store.delete_collection.assert_called_once_with("papers")


async def test_deleting_the_collection_in_use_says_it_will_be_reindexed(
    mock_vector_store, mock_ctx
):
    """Clearing the review's own corpus is allowed, and is a real workflow."""
    mock_vector_store.list_collections.return_value = ["review_blockchain_ia"]
    mock_vector_store.collection_stats.return_value = {"count": 97}
    mock_vector_store.default_collection = "review_blockchain_ia"

    result = await delete_collection("review_blockchain_ia", ctx=mock_ctx)

    assert "the collection this review reads" in result
    assert "re-index into it from scratch" in result


async def test_a_refused_deletion_says_what_exists_instead(mock_vector_store, mock_ctx):
    mock_vector_store.list_collections.return_value = ["papers"]

    result = await delete_collection("review_typo", confirm=True, ctx=mock_ctx)

    assert "No collection named `review_typo`" in result
    assert "`papers`" in result
    mock_vector_store.delete_collection.assert_not_called()


async def test_a_store_that_refuses_the_deletion_is_not_reported_as_done(
    mock_vector_store, mock_ctx
):
    mock_vector_store.list_collections.return_value = ["papers"]
    mock_vector_store.collection_stats.return_value = {"count": 3}
    mock_vector_store.delete_collection.return_value = False

    with pytest.raises(VectorStoreError, match="refused"):
        await delete_collection("papers", confirm=True, ctx=mock_ctx)


async def test_deleting_without_a_store(mock_ctx):
    with patch(
        "academic_hunter.interfaces.mcp.tools.rag._get_vector_store",
        return_value=None,
    ):
        result = await delete_collection("papers", confirm=True, ctx=mock_ctx)

    assert "not available" in result.lower()


async def test_answer_question(mock_vector_store, mock_ctx):
    """Success path — returns the retrieved abstracts and their citations."""
    mock_vector_store.query.return_value = [
        {
            "title": "Relevant Paper",
            "doi": "10.1234/paper",
            "semantic_relevance": 0.92,
            "year": 2024,
            "abstract_preview": "This paper discusses important concepts about machine learning.",
        }
    ]

    result = await answer_question("What is the main finding?", ctx=mock_ctx, top_k=5)

    assert "Retrieved Context" in result
    assert "What is the main finding?" in result
    assert "Relevant Paper" in result
    assert "10.1234/paper" in result
    assert "Retrieved Abstracts" in result
    assert "Sources" in result
    mock_vector_store.query.assert_called_once()
    mock_ctx.info.assert_called()


async def test_the_finding_is_not_the_preview_chopped_mid_sentence(mock_vector_store, mock_ctx):
    """The 250-character cut landed inside a sentence, under a findings heading.

    The preview arrives already truncated to 500 characters by the index, so a raw
    slice at 250 ends mid-word and the agent reads the fragment as a finding. The
    excerpt now ends where the abstract does, at a sentence boundary.
    """
    abstract = (
        "Ledgers settle obligations without a central counterparty. "
        "The throughput of a permissioned network depends on its consensus rule. "
        "We measure four configurations across two workloads and report the trade-off. "
        "A second workload doubles the ledger size and the effect reverses."
    )
    assert len(abstract) > 250
    mock_vector_store.query.return_value = [
        {
            "title": "Relevant Paper",
            "doi": "10.1234/paper",
            "semantic_relevance": 0.92,
            "year": 2024,
            "abstract_preview": abstract,
        }
    ]

    result = await answer_question("throughput", ctx=mock_ctx)

    finding = next(line for line in result.splitlines() if line.startswith("- Ledgers"))
    quoted = finding[len("- "):]
    assert quoted != abstract[:250]
    assert quoted.endswith(".")
    assert len(quoted) < 250
    assert abstract.startswith(quoted)


def test_the_published_description_does_not_promise_synthesis():
    """The description is what the agent reads before deciding to call the tool."""
    described = answer_question.__doc__

    assert "synthesis" not in described.lower()
    assert "synthesise" not in described.lower()
    assert "retriev" in described.lower()


def test_a_first_sentence_longer_than_the_limit_is_not_clipped():
    """Half a sentence is worse than a long one: the text is retrieved, not written."""
    from academic_hunter.interfaces.mcp.tools.rag import _opening

    abstract = "A single sentence that runs well past the limit " + "and keeps going " * 20

    assert _opening(abstract) == abstract.strip()


def test_an_excerpt_shorter_than_the_limit_is_untouched():
    from academic_hunter.interfaces.mcp.tools.rag import _opening

    assert _opening("Short. And complete.") == "Short. And complete."



async def test_answer_question_no_results(mock_vector_store, mock_ctx):
    """Empty vector store returns a helpful message."""
    mock_vector_store.query.return_value = []

    result = await answer_question("unknown topic", ctx=mock_ctx)

    assert "No relevant papers found" in result
    mock_ctx.info.assert_called()


async def test_answer_question_store_unavailable(mock_ctx):
    """When vector store cannot be initialised, return meaningful error."""
    with patch(
        "academic_hunter.interfaces.mcp.tools.rag._get_vector_store",
        return_value=None,
    ):
        with pytest.raises(VectorStoreError, match="[Vv]ector store"):
            await answer_question("test", ctx=mock_ctx)


async def test_rerank_search_basic(mock_vector_store, mock_ctx):
    """Returns re-ranked search results.

    The patch targets ``sentence_transformers.CrossEncoder`` — the package
    attribute — because the production code does ``from sentence_transformers
    import CrossEncoder``. Patching ``sentence_transformers.cross_encoder``
    instead leaves the package attribute bound to the real class, so the mock is
    never consulted: the test then loads the real model and passes either way.
    That is what this test used to do; the two assertions below are what make it
    fail when the reranker is not wired up.
    """
    from academic_hunter.interfaces.mcp.tools.rag import rerank_search

    mock_vector_store.query.return_value = [
        {"title": "Paper A", "semantic_relevance": 0.95},
        {"title": "Paper B", "semantic_relevance": 0.87},
    ]

    with patch("sentence_transformers.CrossEncoder") as m_ce:
        instance = MagicMock()
        instance.predict.return_value = [0.9, 0.8]
        m_ce.return_value = instance

        result = await rerank_search(mock_ctx, "test", top_k=10, rerank_k=5)
        assert "Re-Ranked" in result
        assert "Paper A" in result
        mock_ctx.info.assert_called()
        m_ce.assert_called_once()
        instance.predict.assert_called_once()


async def test_rerank_search_reuses_the_cached_model(mock_vector_store, mock_ctx):
    """Two searches load the cross-encoder once, not once per call.

    Loading the model costs ~5.9 s on CPU and used to be paid on every call.
    The regression this pins: with the model constructed inline in
    ``rerank_search``, ``m_ce`` is called twice.
    """
    from academic_hunter.interfaces.mcp.tools.rag import rerank_search

    mock_vector_store.query.return_value = [{"title": "Paper A", "semantic_relevance": 0.9}]

    with patch("sentence_transformers.CrossEncoder") as m_ce:
        instance = MagicMock()
        instance.predict.return_value = [0.9]
        m_ce.return_value = instance

        await rerank_search(mock_ctx, "first", top_k=10, rerank_k=5)
        await rerank_search(mock_ctx, "second", top_k=10, rerank_k=5)

        assert m_ce.call_count == 1, (
            f"the model was constructed {m_ce.call_count} times; it must be cached"
        )
        assert instance.predict.call_count == 2, "both searches must actually rerank"


async def test_rerank_search_no_results(mock_vector_store, mock_ctx):
    """Returns message when no results."""
    from academic_hunter.interfaces.mcp.tools.rag import rerank_search

    mock_vector_store.query.return_value = []

    result = await rerank_search(mock_ctx, "unknown")
    assert "No semantically relevant" in result
