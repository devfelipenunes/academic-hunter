"""The duplicate merge must not hold the ingest lock while it embeds.

The screener call is the most expensive step in the ingest, and the lock it used
to sit behind is the global one shared by every connector thread — so one thread
embedding a duplicate stalled all the others.
"""

import json
import threading
from unittest.mock import MagicMock

import pytest

from academic_hunter.core.infra import HunterConfig, SearchState
from academic_hunter.core.nlp import AcademicScorer
from academic_hunter.core.screening.resolvers import PaperResolver

CONFIG = {
    "settings": {
        "title_multiplier": 1.5,
        "score_precision": 1,
        "min_relevance_score": 0.0,
        "ablation": {"mode": "hybrid"},
    },
    "anchors": {"cat": ["blockchain"]},
    "technical_strings": {"cat": ["latency"]},
    "technical_weights": {"blockchain": 5.0},
}

PAPER = {
    "Title": "Blockchain latency",
    "Abstract": "An abstract long enough to be preferred over the shorter one.",
    "Year": "2024",
    "Source": "Mock",
    "Citations": 3,
    "Type": "article",
    "Venue": "Mock Venue",
    "URL": "http://example.com",
}


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(CONFIG))
    return HunterConfig(config_path=str(path))


def make_resolver(config, lock, screener):
    scorer = AcademicScorer(
        anchors=config.anchors,
        tech_strings=config.tech_strings,
        tech_weights=config.tech_weights,
        context_rules=config.context_rules,
        settings=config.settings,
    )
    return PaperResolver(
        state=SearchState(),
        scorer=scorer,
        config=config,
        connectors={},
        lock=lock,
        semantic_screener=screener,
    )


def test_another_thread_can_take_the_lock_while_embedding(config):
    """The probe is the test: a second thread tries the lock during the call."""
    lock = threading.RLock()
    observed = {}

    def fake_evaluate(paper, screener_config):
        def probe():
            got = lock.acquire(timeout=1.0)
            observed["free"] = got
            if got:
                lock.release()

        thread = threading.Thread(target=probe)
        thread.start()
        thread.join()
        return 0.5

    screener = MagicMock()
    screener.evaluate.side_effect = fake_evaluate

    resolver = make_resolver(config, lock, screener)
    existing = dict(PAPER)
    other = {**PAPER, "Abstract": "A different abstract, also reasonably long.", "Source": "Other"}

    resolver.resolve_existing_duplicate(existing, other, "cat", "cat", "Other")

    assert screener.evaluate.called, "the fixture did not exercise the screener"
    assert observed.get("free") is True, (
        "the ingest lock was held while the screener ran, so every connector "
        "thread waited on one embedding"
    )


def test_the_score_still_uses_the_embedded_value(config):
    """Moving the work out must not change the number it feeds."""
    lock = threading.RLock()
    screener = MagicMock()
    screener.evaluate.return_value = 0.75

    resolver = make_resolver(config, lock, screener)
    existing = dict(PAPER)

    resolver.resolve_existing_duplicate(existing, dict(PAPER), "cat", "cat", "Mock")

    assert existing["_sem_score"] == 0.75
    assert existing["_hybrid_score"] > 0
