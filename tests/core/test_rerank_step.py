"""Tests for the opt-in cross-encoder rerank stage inside ``RecomputeRanksStep``.

The baseline is a run *without* ``settings.rerank`` — the honest control, and
the cheap one: the stubbed cross-encoder is never reached, so nothing here loads
a real model.
"""

import logging
import threading
from unittest.mock import MagicMock, patch

import pytest

from academic_hunter.core.pipeline.steps import RecomputeRanksStep

QUERY = {"ranking_query": "self-sovereign identity"}
ENABLED = {**QUERY, "rerank": {"enabled": True}}


def make_step(papers, settings=None):
    """A RecomputeRanksStep over a real dict of papers.

    Mirrors ``test_ranking_query.py``: ``semantic_screener`` is None so the
    embedding signal is flat and the sparse signal decides the baseline order.
    """
    hunter = MagicMock()
    hunter.settings = {"min_relevance_score": 0.0, **(settings or {})}
    hunter.lock = threading.RLock()
    hunter.state.stats = {"reranked": 0}
    hunter.semantic_screener = None
    hunter.config.screener_config.return_value = {}
    hunter.scorer.calculate_score.return_value = 0.0
    hunter.consolidated_results = papers
    return RecomputeRanksStep(hunter)


def sample_papers():
    """Fresh dict per call — `run()` writes diagnostics back into the papers."""
    return {
        "a": {"Title": "Hyperledger Fabric performance", "Abstract": "consensus latency"},
        "b": {"Title": "Self-sovereign identity", "Abstract": "digital identity wallets"},
        "c": {"Title": "Unrelated work", "Abstract": "astrophysics"},
    }


def baseline(settings=QUERY):
    """Run the step with no rerank: the ranking the stage must preserve on failure."""
    papers = sample_papers()
    make_step(papers, settings).run()
    return {k: p["Relevance_Score"] for k, p in papers.items()}


def prefer(fragment, hit=0.9, miss=0.1):
    """A cross-encoder stub that likes whichever text contains ``fragment``.

    Keyed on the text rather than on position so the test does not need to know
    what order BM25 happened to produce.
    """
    def side_effect(query, texts, **kwargs):
        return [hit if fragment in t else miss for t in texts]

    return side_effect


def run_with_stub(papers, step, side_effect):
    with patch(
        "academic_hunter.core.pipeline.steps.rerank_texts", side_effect=side_effect
    ) as m:
        step.run()
    return m


# ── off by default, and inert when it cannot work ───────────────────────────


def test_disabled_by_default_leaves_every_score_untouched():
    """Guard, not a regression test: it passes with the stage absent entirely."""
    papers = sample_papers()

    make_step(papers, QUERY).run()  # no `rerank` key at all

    assert {k: p["Relevance_Score"] for k, p in papers.items()} == baseline()
    assert all("_rerank_score" not in p for p in papers.values())


def test_enabled_without_a_query_warns_and_does_not_rerank(caplog):
    """The cross-encoder scores a (query, document) pair; with no query there is none."""
    papers = sample_papers()

    with caplog.at_level(logging.WARNING, logger="academic_hunter.pipeline"):
        make_step(papers, {"rerank": {"enabled": True}}).run()

    assert any("ranking_query" in r.message for r in caplog.records), (
        "configuring the rerank without a query must say so"
    )
    assert all("_rerank_score" not in p for p in papers.values())


def test_an_unavailable_model_leaves_the_scores_untouched():
    papers = sample_papers()
    step = make_step(papers, ENABLED)

    m = run_with_stub(papers, step, lambda *a, **k: None)  # returns None when absent

    m.assert_called_once()
    assert {k: p["Relevance_Score"] for k, p in papers.items()} == baseline()
    assert step.hunter.state.stats["reranked"] == 0


def test_a_failing_model_leaves_the_scores_untouched():
    """Guard: pins the failure path, and passes with the stage absent too.

    An exception from inference must not escape the step.
    """
    papers = sample_papers()
    step = make_step(papers, ENABLED)

    with patch(
        "academic_hunter.core.pipeline.steps.rerank_texts",
        side_effect=RuntimeError("CUDA on fire"),
    ):
        step.run()  # must not raise

    assert {k: p["Relevance_Score"] for k, p in papers.items()} == baseline()
    assert step.hunter.state.stats["reranked"] == 0


def test_a_non_finite_score_leaves_the_scores_untouched():
    """Guard: passes with the stage absent too.

    A NaN compares false against everything and would scramble the head.
    """
    papers = sample_papers()
    step = make_step(papers, ENABLED)

    run_with_stub(papers, step, lambda q, texts, **k: [float("nan")] * len(texts))

    assert {k: p["Relevance_Score"] for k, p in papers.items()} == baseline()
    assert step.hunter.state.stats["reranked"] == 0


def test_too_few_papers_skips_the_rerank():
    papers = {"a": {"Title": "Only paper", "Abstract": "alone"}}
    step = make_step(papers, ENABLED)

    m = run_with_stub(papers, step, prefer("Only"))

    m.assert_not_called()
    assert step.hunter.state.stats["reranked"] == 0


# ── when it does run ────────────────────────────────────────────────────────


def test_enabled_with_a_query_reranks_the_head():
    """The document the cross-encoder prefers must end up on top."""
    papers = sample_papers()
    step = make_step(papers, ENABLED)
    before = baseline()

    # BM25 likes "b" (it matches the query); the cross-encoder overrules it.
    run_with_stub(papers, step, prefer("astrophysics"))

    after = {k: p["Relevance_Score"] for k, p in papers.items()}
    assert after["c"] == max(after.values()), "the cross-encoder's pick must lead"
    assert after["c"] > before["c"], "and it must beat its own baseline position"


def test_the_reranked_head_keeps_its_own_band():
    """Guard: the band is preserved by construction, so removing the stage also passes.

    What it catches is a *future* rule that invents or destroys score — the
    failure mode a naive normalisation would introduce.
    """
    papers = sample_papers()
    step = make_step(papers, ENABLED)
    before = baseline()

    run_with_stub(papers, step, prefer("astrophysics"))
    after = {k: p["Relevance_Score"] for k, p in papers.items()}

    assert max(after.values()) == max(before.values())
    assert min(after.values()) == min(before.values())


def test_only_the_top_n_carry_rerank_diagnostics():
    papers = sample_papers()
    step = make_step(papers, {**QUERY, "rerank": {"enabled": True, "top_n": 2}})

    run_with_stub(papers, step, prefer("astrophysics"))

    scored = [k for k, p in papers.items() if "_rerank_score" in p]
    assert len(scored) == 2, "top_n bounds how many are scored"


def test_the_stat_counts_what_moved_not_what_was_scored():
    """The counter reports the effect, the diagnostics report what was said.

    With two candidates that already sit at the band's extremes the lattice has
    nowhere to move them, so the cross-encoder runs, the diagnostics land, and
    nothing changes. A counter that reported "2 reranked" there would claim an
    order the exported scores do not carry.
    """
    papers = sample_papers()
    step = make_step(papers, {**QUERY, "rerank": {"enabled": True, "top_n": 2}})

    run_with_stub(papers, step, prefer("astrophysics"))

    scored = [k for k, p in papers.items() if "_rerank_score" in p]
    assert len(scored) == 2, "the cross-encoder did score both candidates"
    assert step.hunter.state.stats["reranked"] == 0, (
        "nothing moved, so nothing was reranked"
    )


def test_the_rank_diagnostic_records_the_new_position():
    papers = sample_papers()
    step = make_step(papers, ENABLED)

    run_with_stub(papers, step, prefer("astrophysics"))

    ranks = {k: p.get("_rerank_rank") for k, p in papers.items() if "_rerank_rank" in p}
    assert sorted(ranks.values()) == [1, 2, 3]
    assert ranks["c"] == 1


def test_the_cross_encoder_receives_title_and_abstract():
    """The same representation the BM25 index in the step is built on."""
    papers = sample_papers()
    step = make_step(papers, ENABLED)

    m = run_with_stub(papers, step, prefer("astrophysics"))

    texts = m.call_args.args[1]
    assert any("Unrelated work" in t and "astrophysics" in t for t in texts)


def test_the_score_precision_setting_is_read():
    """`Relevance_Score` used to be rounded to one decimal regardless.

    The rerank made the disagreement matter: its lattice is built at the written
    precision, so a finer lattice than the rounding would be erased and take the
    order with it. Anything unusable falls back rather than raising.
    """
    from academic_hunter.core.pipeline.steps import _score_decimals

    assert _score_decimals({"score_precision": 3}) == 3
    assert _score_decimals({"score_precision": 0}) == 0
    assert _score_decimals({}) == 1
    assert _score_decimals({"score_precision": "dois"}) == 1
    assert _score_decimals({"score_precision": None}) == 1
    assert _score_decimals({"score_precision": -1}) == 1


def test_invalid_top_n_falls_back_to_the_default():
    papers = sample_papers()
    step = make_step(papers, {**QUERY, "rerank": {"enabled": True, "top_n": "vinte"}})

    run_with_stub(papers, step, prefer("astrophysics"))

    # Falls back to 20, which exceeds the three papers here, so all are scored.
    scored = [k for k, p in papers.items() if "_rerank_score" in p]
    assert len(scored) == 3


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
