"""Tests for ranking against a configured query.

When ``settings.ranking_query`` is set, the sparse signal switches from the
domain-term count to BM25 over that query. The domain count answers "does this
paper look like the domain?" — it never sees a question. Measured on the judged
collection, having an actual query is what moved nDCG@10 from 0.28 to 0.67.

The default weights in query mode are BM25 alone, because adding the embedding
lowered the score monotonically in that measurement.
"""

import threading
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


def test_the_citation_signal_does_not_move_the_query_ranking():
    """Query mode is the configuration that ships, and its ordering is pinned here.

    The citation component exists and is computed on every run; with the default
    weight of zero it must leave ``Relevance_Score`` exactly as it was, paper by
    paper. A run that reorders without anyone touching ``fusion_weights`` is a
    regression, not a feature.
    """
    def scored(citations, weights=None):
        papers = sample_papers()
        for slug, count in citations.items():
            papers[slug]["Citations"] = count
        settings = {"ranking_query": "self-sovereign identity"}
        if weights:
            settings["fusion_weights"] = weights
        make_step(papers, settings).run()
        return {slug: paper["Relevance_Score"] for slug, paper in papers.items()}

    baseline = scored({})
    assert scored({"a": 410, "b": 75, "c": 0}) == baseline
    assert scored({"a": 410, "b": 75, "c": 0}, {"keyword": 1.0, "embedding": 0.0}) == baseline


def test_query_mode_records_the_citation_signal_for_calibration():
    papers = sample_papers()
    papers["a"]["Citations"] = 9
    step = make_step(papers, {"ranking_query": "self-sovereign identity"})

    step.run()

    assert papers["a"]["_citation_score"] == 1.0
    assert papers["b"]["_citation_score"] == 0.0


def test_query_mode_records_the_weights_it_forced():
    """The 1.0/0.0 above is a decision taken here, and the run has to admit it.

    ``ranking_query`` set and ``fusion_weights`` absent is the configuration
    that ships, and it silently overrides the config's defaults. The recorded
    weights are the applied ones, so the artifact alone answers "why is this
    ordering keyword-only?".
    """
    step = make_step(sample_papers(), {"ranking_query": "self-sovereign identity"})

    step.run()

    fusion = step.hunter.state.stats["fusion"]
    assert fusion["weights"] == {"keyword": 1.0, "embedding": 0.0, "citation": 0.0}
    assert fusion["strategy"] == "weighted_norm"


def test_an_explicit_weight_in_query_mode_overrides_the_forced_pair():
    """A configured weight wins, which is why the key's absence is not neutral."""
    papers = sample_papers()
    for slug, sem in (("a", 0.1), ("b", 0.9), ("c", 0.2)):
        papers[slug]["_sem_score"] = sem
    step = make_step(papers, {
        "ranking_query": "self-sovereign identity",
        "fusion_weights": {"keyword": 0.5, "embedding": 0.5},
    })

    step.run()

    fusion = step.hunter.state.stats["fusion"]
    assert fusion["weights"]["embedding"] == 0.5
    assert "embedding" not in fusion["discarded"]
