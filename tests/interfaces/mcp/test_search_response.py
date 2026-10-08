"""What the search reply says about the signals behind the ranking.

The reply already names the sources that never ran, because a zero from a source
that was not asked is not a finding. A signal that was computed and then
weighted zero is the same kind of number: the ranking looks like the work of
three signals and is the work of one, and nothing else in the reply says so.
"""

from unittest.mock import MagicMock

from academic_hunter.interfaces.mcp.tools.search import _coverage


def hunter_with(stats):
    hunter = MagicMock()
    hunter.query_history = [{"Source": "OpenAlex"}]
    hunter.stats = {"identified": {"OpenAlex": 3}, "included_final": 2, **stats}
    hunter.blocked_sources = set()
    hunter.connectors = {}
    hunter.config.anchors = {}
    hunter.config.tech_strings = {}
    hunter.semantic_screener = None
    return hunter


def test_the_reply_names_a_signal_that_was_computed_and_weighted_zero():
    hunter = hunter_with(
        {
            "fusion": {
                "strategy": "weighted_norm",
                "weights": {"keyword": 1.0, "embedding": 0.0, "citation": 0.0},
                "discarded": ["embedding"],
            }
        }
    )

    text = _coverage(hunter)

    assert "embedding" in text, "a signal was computed, thrown away, and not mentioned"
    assert "weighted 0" in text or "weighted zero" in text


def test_the_reply_says_nothing_when_every_signal_counted():
    hunter = hunter_with(
        {
            "fusion": {
                "strategy": "weighted_norm",
                "weights": {"keyword": 0.7, "embedding": 0.3, "citation": 0.0},
                "discarded": [],
            }
        }
    )

    text = _coverage(hunter)

    assert "weighted 0" not in text and "weighted zero" not in text


def test_a_hunter_with_no_recorded_weights_still_answers():
    """The block is new: a run or a caller without it must not break the reply."""
    text = _coverage(hunter_with({}))

    assert "Coverage by source:" in text
