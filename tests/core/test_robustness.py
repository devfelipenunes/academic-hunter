"""Regression tests for the Fase 0.5 robustness fixes.

Each test here pins a defect that was live in the codebase:

- ``math.sqrt`` on a signed cosine raised ``ValueError``.
- The dedup check and the dedup claim happened under two separate lock
  acquisitions, so two threads could both register the same paper.
- The SQLite stores promised thread safety but ran with SQLite's default
  rollback journal and no busy timeout.
"""

import json
import sqlite3
import threading

import pytest

from academic_hunter.core.infra import HunterConfig, SearchState
from academic_hunter.core.infra.cache import SQLiteCache
from academic_hunter.core.nlp import AcademicScorer
from academic_hunter.core.screening.processor import PaperProcessor

BASE_CONFIG = {
    "settings": {
        "title_multiplier": 1.5,
        "score_precision": 1,
        "min_relevance_score": 0.0,
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
def scorer(config):
    return AcademicScorer(
        anchors=config.anchors,
        tech_strings=config.tech_strings,
        tech_weights=config.tech_weights,
        context_rules=config.context_rules,
        settings=config.settings,
    )


# ── sqrt clamp ──────────────────────────────────────────────────────────────


def test_hybrid_score_survives_negative_cosine(scorer):
    """A negative cosine means "no semantic relevance", not a crash.

    Cosine similarity is signed, so an anti-correlated pair yields a negative
    value and ``math.sqrt`` raises ``ValueError`` on it. One bad pair used to be
    able to abort a run.
    """
    score = scorer.compute_hybrid_score(
        title="Blockchain latency",
        abstract="Blockchain latency",
        citations=0,
        semantic_score=-0.42,
        has_semantic=True,
        ablation_mode="embedding",
    )

    assert score == 0.0


def test_fused_score_survives_negative_cosine(scorer):
    """The fused branch keeps its keyword bonus when the cosine is negative."""
    score = scorer.compute_hybrid_score(
        title="Blockchain latency",
        abstract="Blockchain latency",
        citations=0,
        semantic_score=-0.42,
        has_semantic=True,
        ablation_mode="hybrid",
    )

    # sqrt(clamp(-0.42)) * 10 == 0, so only the keyword term survives.
    kw_only = scorer.calculate_score("Blockchain latency", "Blockchain latency", 0)
    assert score == pytest.approx(round(kw_only * 0.3, 1))


def test_positive_cosine_is_unchanged_by_the_clamp(scorer):
    """The clamp must not alter the normal path."""
    expected = round((0.25 ** 0.5) * 10.0, 1)

    assert scorer.compute_hybrid_score(
        title="t", abstract="a", citations=0,
        semantic_score=0.25, has_semantic=True, ablation_mode="embedding",
    ) == expected


# ── dedup atomicity ─────────────────────────────────────────────────────────


def _make_processor(config, scorer):
    state = SearchState()
    return PaperProcessor(
        state=state,
        scorer=scorer,
        config=config,
        connectors={},
        lock=threading.RLock(),
        semantic_screener=None,
    )


def test_concurrent_duplicate_submission_registers_once(config, scorer, monkeypatch):
    """Many threads submitting the same paper must produce one registration.

    ``process`` used to check ``seen_ids`` under one lock acquisition and add to
    it under another, so concurrent threads could all conclude "new" and each
    register the paper.

    The window between those two acquisitions is only a few bytecodes wide, so
    reproducing the collision by timing alone would be a flaky test. Instead this
    asserts the mechanism that closes the window: computing the dedup key is
    part of the decision, so it must happen *inside* the critical section. With
    a deliberately slow slug computation, the old code let all threads compute
    it concurrently (they were outside the lock) and every one of them then saw
    an empty ``seen_ids``; the new code serialises it, so at most one thread is
    ever inside.
    """
    import time

    processor = _make_processor(config, scorer)

    real_generate_slug = scorer.generate_slug
    concurrent_now = 0
    max_concurrent_seen = 0

    def slow_generate_slug(title):
        nonlocal concurrent_now, max_concurrent_seen
        concurrent_now += 1
        max_concurrent_seen = max(max_concurrent_seen, concurrent_now)
        try:
            time.sleep(0.01)
            return real_generate_slug(title)
        finally:
            concurrent_now -= 1

    monkeypatch.setattr(scorer, "generate_slug", slow_generate_slug)

    threads_n = 16
    barrier = threading.Barrier(threads_n)

    def submit():
        # Line every thread up so they collide inside the critical section.
        barrier.wait()
        processor.process(
            paper={
                "Title": "Blockchain latency",
                "Abstract": "Blockchain latency measurement.",
                "Year": "2024",
                "Source": "Mock",
                "Citations": 0,
                "Type": "article",
                "Venue": "Mock Venue",
            },
            anchor_cat="cat",
            tech_cat="cat",
            anchor_list=["blockchain"],
            tech_list=["latency"],
        )

    threads = [threading.Thread(target=submit) for _ in range(threads_n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert max_concurrent_seen == 1, (
        "the dedup decision (including its key computation) must be made under "
        "the lock; letting threads compute it concurrently is what let them all "
        "conclude 'new' at once"
    )
    assert len(processor.state.consolidated_results) == 1, (
        "the same paper must be registered exactly once"
    )
    assert processor.state.stats["duplicates_removed"] == threads_n - 1


def test_concurrent_distinct_papers_are_all_registered(config, scorer):
    """The atomic claim must not drop genuinely distinct papers."""
    processor = _make_processor(config, scorer)
    threads_n = 16
    barrier = threading.Barrier(threads_n)

    def submit(i):
        barrier.wait()
        processor.process(
            paper={
                "Title": f"Blockchain latency study {i}",
                "Abstract": "Blockchain latency measurement.",
                "Year": "2024",
                "Source": "Mock",
                "Citations": 0,
                "Type": "article",
                "Venue": "Mock Venue",
            },
            anchor_cat="cat",
            tech_cat="cat",
            anchor_list=["blockchain"],
            tech_list=["latency"],
        )

    threads = [threading.Thread(target=submit, args=(i,)) for i in range(threads_n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(processor.state.consolidated_results) == threads_n
    assert processor.state.stats["duplicates_removed"] == 0


# ── sqlite concurrency settings ─────────────────────────────────────────────


def test_cache_uses_wal_journal(tmp_path):
    """WAL is what lets a reader proceed while a writer holds the lock."""
    db_path = tmp_path / "cache.db"
    SQLiteCache(db_path=str(db_path))

    mode = sqlite3.connect(db_path).execute("PRAGMA journal_mode").fetchone()[0]

    assert mode.lower() == "wal"


def test_cache_roundtrip_still_works(tmp_path):
    """The connection change must not break the read/write path."""
    cache = SQLiteCache(db_path=str(tmp_path / "cache.db"))
    cache.set("k", "v")

    assert cache.get("k") == "v"
    assert cache.get("missing") is None
