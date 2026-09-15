"""Tests for ranking against a configured query.

When ``settings.ranking_query`` is set, the sparse signal switches from the
domain-term count to BM25 over that query. The domain count answers "does this
paper look like the domain?" — it never sees a question. Measured on the judged
collection, having an actual query is what moved nDCG@10 from 0.28 to 0.67.

The default weights in query mode are BM25 alone, because adding the embedding
lowered the score monotonically in that measurement.
"""

import threading

import pytest
from unittest.mock import MagicMock

from academic_hunter.core.pipeline.steps import RecomputeRanksStep


def make_step(papers, settings=None):
    """A RecomputeRanksStep over a real dict of papers.

    ``semantic_screener`` is None so every ``_sem_score`` falls back to 0.0:
    that isolates the sparse signal, which is what these tests are about.
    """
    hunter = MagicMock()
    hunter.settings = {"min_relevance_score": 0.0, **(settings or {})}
    hunter.lock = threading.RLock()
    hunter.state.stats = {}
    hunter.semantic_screener = None
    hunter.config.screener_config.return_value = {}
    hunter.scorer.calculate_score.return_value = 0.0
    hunter.consolidated_results = papers
    return RecomputeRanksStep(hunter)


def sample_papers():
    """A fresh dict each call.

    Module-level state would leak between tests: `run()` writes diagnostics
    back into the paper dicts, so a shared fixture makes the second test see
    the first test's leftovers.
    """
    return {
        "a": {"Title": "Hyperledger Fabric performance", "Abstract": "consensus latency"},
        "b": {"Title": "Self-sovereign identity", "Abstract": "digital identity wallets"},
        "c": {"Title": "Unrelated work", "Abstract": "astrophysics"},
    }


def test_query_mode_records_a_bm25_score():
    papers = sample_papers()
    step = make_step(papers, {"ranking_query": "self-sovereign identity"})

    step.run()

    assert "_bm25_score" in papers["b"]
    assert papers["c"].get("_bm25_score", 0.0) == 0.0


def test_the_matching_paper_ranks_first():
    papers = sample_papers()
    step = make_step(papers, {"ranking_query": "self-sovereign identity"})

    step.run()

    assert papers["b"]["Relevance_Score"] > papers["a"]["Relevance_Score"]
    assert papers["b"]["Relevance_Score"] > papers["c"]["Relevance_Score"]


def test_a_non_matching_paper_scores_zero():
    papers = sample_papers()
    step = make_step(papers, {"ranking_query": "self-sovereign identity"})

    step.run()

    assert papers["c"]["Relevance_Score"] == 0.0


def test_without_a_query_nothing_changes():
    """No query means the domain-term signal, exactly as before."""
    papers = sample_papers()
    step = make_step(papers)

    step.run()

    assert all("_bm25_score" not in p for p in papers.values())


def test_a_blank_query_is_treated_as_absent():
    """Whitespace is what an empty settings field looks like after a round-trip."""
    papers = sample_papers()
    step = make_step(papers, {"ranking_query": "   "})

    step.run()

    assert all("_bm25_score" not in p for p in papers.values())


def test_query_mode_defaults_to_bm25_alone():
    """The embedding must not move the ranking unless explicitly weighted in.

    Adding it lowered nDCG@10 monotonically in the measurement that decided
    this default, so an unweighted query-mode run is BM25 only.
    """
    papers = {
        "match": {"Title": "blockchain", "Abstract": "blockchain ledger"},
        "strong_embedding": {"Title": "other", "Abstract": "other"},
    }
    step = make_step(papers, {"ranking_query": "blockchain"})
    # The embedding likes the non-matching paper; BM25 must still win.
    step.hunter.semantic_screener = MagicMock()
    step.hunter.semantic_screener.evaluate.side_effect = lambda p, _c: (
        0.9 if p is papers["strong_embedding"] else 0.0
    )
    papers["strong_embedding"]["_sem_score"] = 0.9
    papers["match"]["_sem_score"] = 0.0

    step.run()

    assert papers["match"]["Relevance_Score"] > papers["strong_embedding"]["Relevance_Score"]


def test_explicit_weights_override_the_query_default():
    """A caller who wants the embedding in can still have it."""
    papers = {
        "match": {"Title": "blockchain ledger", "Abstract": "distributed"},
        "other": {"Title": "unrelated", "Abstract": "astrophysics"},
    }
    step = make_step(papers, {
        "ranking_query": "blockchain",
        "fusion_weights": {"keyword": 0.0, "embedding": 1.0},
    })
    papers["match"]["_sem_score"] = 0.0
    papers["other"]["_sem_score"] = 0.9

    step.run()

    # Weighted entirely on the embedding, so the paper it likes wins despite
    # matching nothing lexically.
    assert papers["other"]["Relevance_Score"] > papers["match"]["Relevance_Score"]


def test_query_mode_still_respects_the_reported_scale():
    papers = sample_papers()
    step = make_step(papers, {"ranking_query": "self-sovereign identity"})

    step.run()

    for paper in papers.values():
        assert 0.0 <= paper["Relevance_Score"] <= 10.0


def test_scores_collapse_when_nothing_matches():
    """A query that matches no paper is evidence for no paper.

    These used to tie at the *top* of the scale, which passed every one of them
    through the threshold. That is the wrong direction for a review — an included
    paper costs a reader more than an empty run — and the run is not silent about
    it: the query it was ranked against is recorded in the report.

    A flat signal that carries something (every paper matched the anchors equally)
    still ties at the top; only the all-zero case drops.
    """
    papers = {"a": {"Title": "alpha", "Abstract": ""}, "b": {"Title": "beta", "Abstract": ""}}
    step = make_step(papers, {"ranking_query": "nothingmatchesthis", "min_relevance_score": 5.0})

    step.run()

    assert [p["Relevance_Score"] for p in papers.values()] == [0.0, 0.0]
