"""Tests for SearchPipeline (pipeline/manager.py).

Covers methods not exercised by the integration-level pipeline tests:
- _index_results
- _recompute_ranks
- vector_store lazy init
"""

import pytest
from unittest.mock import patch, MagicMock, PropertyMock


def _make_hunter_with_results(results_dict):
    """Create a mock hunter with consolidated_results as a real dict."""
    hunter = MagicMock()
    hunter.output_dir = MagicMock()
    hunter.output_dir.parent = MagicMock()
    hunter.state.stats = {}
    type(hunter).consolidated_results = PropertyMock(return_value=results_dict)
    return hunter


# ── vector_store property ───────────────────────────────────────────────────


def test_vector_store_lazy_init():
    """vector_store property initializes ChromaDB on first access."""
    from academic_hunter.core.pipeline.manager import SearchPipeline

    hunter = MagicMock()
    hunter.output_dir.parent = MagicMock()
    pipeline = SearchPipeline(hunter)
    assert pipeline._vector_store is None

    with patch("academic_hunter.plugins.vector_stores.ChromaVectorStore") as m_cs:
        mock_store = MagicMock()
        m_cs.return_value = mock_store
        store = pipeline.vector_store

    assert store == mock_store
    assert pipeline._vector_store == mock_store


def test_vector_store_lazy_init_failure():
    """vector_store returns None on initialization failure."""
    from academic_hunter.core.pipeline.manager import SearchPipeline

    hunter = MagicMock()
    hunter.output_dir.parent = MagicMock()
    pipeline = SearchPipeline(hunter)
    with patch("academic_hunter.plugins.vector_stores.ChromaVectorStore") as m_cs:
        m_cs.side_effect = Exception("Import failed")
        store = pipeline.vector_store

    assert store is None
    assert pipeline._vector_store is None


# ── _index_results ──────────────────────────────────────────────────────────


def test_index_results_no_store():
    """_index_results skips when vector store is None."""
    from academic_hunter.core.pipeline.manager import SearchPipeline

    hunter = MagicMock()
    pipeline = SearchPipeline(hunter)
    pipeline._vector_store = None
    pipeline._index_results()  # should not raise


def test_index_results_no_papers():
    """_index_results skips when no consolidated results."""
    from academic_hunter.core.pipeline.manager import SearchPipeline

    hunter = _make_hunter_with_results({})
    pipeline = SearchPipeline(hunter)
    pipeline._vector_store = MagicMock()
    pipeline._index_results()
    pipeline._vector_store.index_papers.assert_not_called()


def test_index_results_with_papers():
    """_index_results indexes consolidated papers."""
    from academic_hunter.core.pipeline.manager import SearchPipeline

    hunter = _make_hunter_with_results({"p1": {"Title": "Paper"}})
    # IndexResultsStep accesses hunter.pipeline.vector_store
    mock_pipeline = MagicMock()
    mock_vector_store = MagicMock()
    mock_pipeline.vector_store = mock_vector_store
    hunter.pipeline = mock_pipeline

    pipeline = SearchPipeline(hunter)
    pipeline._index_results()
    mock_vector_store.index_papers.assert_called_once_with(
        [{"Title": "Paper"}]
    )


# ── _recompute_ranks ────────────────────────────────────────────────────────


def test_recompute_ranks_no_results():
    """_recompute_ranks skips when no consolidated results."""
    from academic_hunter.core.pipeline.manager import SearchPipeline

    hunter = _make_hunter_with_results({})
    pipeline = SearchPipeline(hunter)
    pipeline._recompute_ranks()  # should not raise


def test_recompute_ranks_single_paper():
    """_recompute_ranks skips when fewer than 2 papers."""
    from academic_hunter.core.pipeline.manager import SearchPipeline

    hunter = _make_hunter_with_results({"p1": {}})
    pipeline = SearchPipeline(hunter)
    pipeline._recompute_ranks()  # should not raise


def test_recompute_ranks_two_papers():
    """_recompute_ranks computes geometric mean ranks for 2 papers."""
    from academic_hunter.core.pipeline.manager import SearchPipeline

    results = {
        "p1": {"Title": "Paper 1", "Abstract": "blockchain tech"},
        "p2": {"Title": "Paper 2", "Abstract": "not relevant at all"},
    }
    hunter = _make_hunter_with_results(results)
    hunter.scorer.calculate_score.side_effect = [10.0, 1.0]
    hunter.semantic_screener = None
    hunter.state.stats = {}
    hunter.settings = {"min_relevance_score": 0.0}

    pipeline = SearchPipeline(hunter)
    pipeline._recompute_ranks()

    # Check that Relevance_Score was set on both papers
    assert "Relevance_Score" in results["p1"]
    assert "Relevance_Score" in results["p2"]
    assert results["p1"]["Relevance_Score"] >= results["p2"]["Relevance_Score"]
