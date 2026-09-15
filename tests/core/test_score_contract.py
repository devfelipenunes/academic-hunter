"""Contract tests for the two-score design.

The pipeline carries two scores that used to share one key, so a single
``min_relevance_score`` constant silently meant two different things depending
on *when* you read it:

- ``_hybrid_score`` — ablation-dependent **inclusion** score, written at ingest.
- ``Relevance_Score`` — rank-normalised **reported** score in [0, 10], written
  once at the end of the run by ``RecomputeRanksStep``.

These tests pin the boundary between them.
"""

import json
import threading

import pytest

from academic_hunter.core.infra import HunterConfig, SearchState
from academic_hunter.core.models import Paper
from academic_hunter.core.nlp import AcademicScorer
from academic_hunter.core.screening.resolvers import PaperResolver

BASE_CONFIG = {
    "settings": {
        "title_multiplier": 1.5,
        "score_precision": 1,
        "min_relevance_score": 5.0,
    },
    "anchors": {"cat": ["blockchain"]},
    "technical_strings": {"cat": ["latency"]},
    "technical_weights": {"blockchain": 5.0, "latency": 2.0},
}


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(BASE_CONFIG))
    return HunterConfig(config_path=str(path))


@pytest.fixture
def resolver(config):
    scorer = AcademicScorer(
        anchors=config.anchors,
        tech_strings=config.tech_strings,
        tech_weights=config.tech_weights,
        context_rules=config.context_rules,
        settings=config.settings,
    )
    # semantic_screener=None keeps the mode effectively keyword-only, so the
    # inclusion score is the raw regex score — a scale we can predict exactly.
    return PaperResolver(
        state=SearchState(),
        scorer=scorer,
        config=config,
        connectors={},
        lock=threading.RLock(),
        semantic_screener=None,
    )


# ── the threshold setting ───────────────────────────────────────────────────


def test_min_inclusion_score_falls_back_to_min_relevance_score(config):
    """Unset override keeps existing configurations behaving as before."""
    assert config.settings["min_relevance_score"] == 5.0
    assert config.min_inclusion_score() == 5.0


def test_min_inclusion_score_can_be_set_independently(config):
    """The two thresholds are separate knobs on separate scales."""
    config.settings["min_inclusion_score"] = 12.0
    config.settings["min_relevance_score"] = 3.5

    assert config.min_inclusion_score() == 12.0


# ── the Paper model footgun ─────────────────────────────────────────────────


def test_paper_constructor_drops_underscore_fields():
    """`Paper.__init__` only copies FIELD_SCHEMA keys.

    Passing diagnostic keys to the constructor silently discards them, which is
    what made RecomputeRanksStep's recompute path load-bearing rather than
    defensive. If this test ever fails, the constructor started preserving
    unknown keys and the post-construction assignments in `resolvers.py` can be
    folded back in.
    """
    paper = Paper({"Title": "X", "_kw_score": 5.0, "_sem_score": 0.3})

    assert "_kw_score" not in paper
    assert "_sem_score" not in paper


def test_paper_preserves_underscore_fields_assigned_after_construction():
    """Post-construction assignment is the supported way to attach diagnostics."""
    paper = Paper({"Title": "X"})
    paper["_hybrid_score"] = 7.5

    assert paper["_hybrid_score"] == 7.5


# ── ingest writes the inclusion score, never the reported one ───────────────


def test_register_new_paper_stores_inclusion_score_under_private_key(resolver):
    """Ingest must not touch `Relevance_Score` — it is owned by RecomputeRanksStep."""
    resolver.register_new_paper(
        paper={
            "Title": "Blockchain latency",
            "Abstract": "Blockchain latency measurement.",
            "Year": "2024",
            "URL": "http://example.com",
            "Source": "Mock",
            "Citations": 0,
            "Type": "article",
            "Venue": "Mock Venue",
        },
        dedup_id="blockchainlatency",
        title="Blockchain latency",
        doi_clean="10.0/mock",
        tech_cat="cat",
        tech_list=["latency"],
        source="Mock",
    )

    paper = resolver.state.consolidated_results["blockchainlatency"]

    assert "_hybrid_score" in paper, "the inclusion score must be recorded"
    assert paper["Relevance_Score"] == 0.0, (
        "Relevance_Score must stay at its default until RecomputeRanksStep runs; "
        "an inclusion score written here put two scales behind one key"
    )


def test_inclusion_gate_uses_min_inclusion_score(resolver):
    """The ingest gate reads its own threshold, not the reported score's.

    Note what the gate does and does not do: it *classifies* a paper
    (included vs. score-excluded in the run statistics) but always stores it.
    Removal from the collection happens later, in RecomputeRanksStep and the
    final qualifier filter — both of which operate on the rank-normalised
    ``Relevance_Score``. So this threshold steers the reported counts, and the
    reporting threshold steers what survives.
    """
    paper = {
        "Title": "Blockchain latency",
        "Abstract": "Blockchain latency measurement.",
        "Year": "2024",
        "Source": "Mock",
        "Citations": 0,
        "Type": "article",
        "Venue": "Mock Venue",
    }

    resolver.register_new_paper(
        paper=dict(paper),
        dedup_id="p1",
        title="Blockchain latency",
        doi_clean="10.0/1",
        tech_cat="cat",
        tech_list=["latency"],
        source="Mock",
    )
    inclusion = resolver.state.consolidated_results["p1"]["_hybrid_score"]
    assert resolver.state.stats["included_final"] == 1

    # Raise only the inclusion threshold, above this paper's score.
    resolver.config.settings["min_inclusion_score"] = inclusion + 1.0

    resolver.register_new_paper(
        paper=dict(paper),
        dedup_id="p2",
        title="Blockchain latency",
        doi_clean="10.0/2",
        tech_cat="cat",
        tech_list=["latency"],
        source="Mock",
    )

    assert resolver.state.stats["included_final"] == 1, "p2 must not count as included"
    assert resolver.state.stats["excluded_technical_score"] == 1, "p2 must count as score-excluded"
    assert "p2" in resolver.state.consolidated_results, (
        "the gate classifies; it does not evict — removal is deferred to the rank step"
    )
