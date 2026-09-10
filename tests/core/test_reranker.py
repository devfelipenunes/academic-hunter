"""Tests for the cross-encoder reranker: the pure remap, the cache, the config.

The remap tests are the load-bearing ones. ``RecomputeRanksStep`` rounds
``Relevance_Score`` to one decimal and every consumer sorts on the rounded
value, so a rerank that reorders scores without accounting for that rounding
silently undoes itself on export.
"""

from unittest.mock import MagicMock, patch

import pytest

from academic_hunter.core.nlp import model_cache
from academic_hunter.core.nlp.reranker import (
    MAX_SCORE,
    rerank_config,
    rerank_scores,
)


def _ce_order(scores):
    """Indices best-first, the way the step derives them from cross-encoder scores."""
    return sorted(range(len(scores)), key=lambda i: (-scores[i], i))


# ── the remap rule ──────────────────────────────────────────────────────────


class TestRerankScores:
    def test_reorders_the_candidates_along_the_new_order(self):
        base = [8.0, 7.0, 6.0, 5.0]
        # The cross-encoder prefers the last document, then the second.
        out = rerank_scores(base, _ce_order([0.1, 0.4, 0.2, 0.9]))

        assert out[3] > out[1] > out[2] > out[0]

    def test_outsiders_are_untouched(self):
        """A document outside the reranked head keeps its exact score."""
        base = [9.0, 8.0, 7.0, 2.5]
        out = rerank_scores(base, [1, 0])  # only the first two are candidates

        assert out[3] == 2.5
        assert out[2] == 7.0

    def test_order_survives_the_one_decimal_rounding(self):
        """The regression the naive remap fails.

        Handing the candidates' own scores back in the new order preserves the
        multiset exactly and is the obvious implementation — but 7.24 and 7.21
        both round to 7.2, and the exporters sort on the rounded value, so the
        tie falls back to insertion order and the rerank disappears. The band
        lattice keeps consecutive ranks distinct *at export precision*.
        """
        base = [7.4, 7.24, 7.21, 7.1]
        ce = _ce_order([0.1, 0.2, 0.3, 0.9])  # reversed: 3, 2, 1, 0
        out = rerank_scores(base, ce)

        # The naive rule would produce rounded values [7.1, 7.2, 7.2, 7.4]:
        # ranks 1 and 2 tie and the order is lost.
        rounded = [round(out[i], 1) for i in ce]
        assert rounded == sorted(rounded, reverse=True), "export order must descend"
        assert len(set(rounded)) == len(ce), "each rank needs a distinct exported score"

    def test_reranked_values_are_distinct_at_export_precision(self):
        base = [9.4, 9.1, 8.8, 8.5, 8.2, 7.9, 7.6, 7.3, 7.0, 6.7]
        out = rerank_scores(base, _ce_order([(i * 7) % 10 for i in range(10)]))

        exported = [round(s, 1) for s in out]
        assert len(set(exported)) == len(base)

    def test_scores_stay_inside_the_candidate_band(self):
        base = [8.8, 8.1, 7.4, 6.9]
        out = rerank_scores(base, _ce_order([0.5, 0.1, 0.9, 0.3]))

        assert max(out) == round(max(base), 1)
        assert min(out) == round(min(base), 1)

    def test_scores_stay_within_the_scale(self):
        base = [10.0, 9.5, 9.0, 0.2, 0.1]
        out = rerank_scores(base, _ce_order([0.4, 0.3, 0.2, 0.1, 0.9]))

        assert all(0.0 <= s <= MAX_SCORE for s in out)

    def test_the_ce_best_takes_the_band_ceiling(self):
        base = [8.8, 8.1, 7.4, 6.9]
        ce = _ce_order([0.1, 0.2, 0.3, 0.9])
        out = rerank_scores(base, ce)

        assert out[ce[0]] == round(max(base), 1)

    def test_a_narrow_band_reranks_fewer_candidates(self):
        """Twenty candidates wedged into 9.9-10.0 cannot take twenty distinct values.

        The band is never widened to make room — that would push papers past the
        floor their own peers set — so the set is trimmed instead.
        """
        base = [10.0] + [9.9] * 19
        out = rerank_scores(base, _ce_order(list(range(20))))

        assert min(out) >= round(min(base), 1)
        assert max(out) <= MAX_SCORE

    def test_tied_candidates_are_left_alone(self):
        """Nothing to decide when every candidate carries the same score."""
        base = [7.0, 7.0, 7.0]
        assert rerank_scores(base, [2, 1, 0]) == base

    def test_a_single_candidate_is_a_no_op(self):
        base = [7.0, 3.0]
        assert rerank_scores(base, [0]) == base

    def test_an_empty_candidate_list_is_a_no_op(self):
        base = [7.0, 3.0]
        assert rerank_scores(base, []) == base

    def test_a_repeated_candidate_keeps_its_first_place(self):
        """A duplicated index must not overwrite its own better position."""
        base = [8.0, 5.0, 2.0]
        out = rerank_scores(base, [0, 0, 2])

        assert out[0] >= out[2]
        assert out[1] == 5.0


# ── the model cache ─────────────────────────────────────────────────────────


class TestModelCache:
    def test_the_cross_encoder_is_loaded_once(self):
        with patch("sentence_transformers.CrossEncoder") as m_ce:
            m_ce.return_value = MagicMock()

            first = model_cache.get_cross_encoder()
            second = model_cache.get_cross_encoder()

            assert first is second
            assert m_ce.call_count == 1, (
                f"the model was constructed {m_ce.call_count} times; it must be cached"
            )

    def test_a_different_max_length_loads_a_second_model(self):
        """Truncation is part of the model's identity, not a later tweak."""
        with patch("sentence_transformers.CrossEncoder") as m_ce:
            m_ce.return_value = MagicMock()

            model_cache.get_cross_encoder(max_length=512)
            model_cache.get_cross_encoder(max_length=128)

            assert m_ce.call_count == 2

    def test_clear_model_cache_forces_a_reload(self):
        with patch("sentence_transformers.CrossEncoder") as m_ce:
            m_ce.return_value = MagicMock()

            model_cache.get_cross_encoder()
            model_cache.clear_model_cache()
            model_cache.get_cross_encoder()

            assert m_ce.call_count == 2

    def test_sentence_transformer_is_loaded_once(self):
        with patch("sentence_transformers.SentenceTransformer") as m_st:
            m_st.return_value = MagicMock()

            first = model_cache.get_sentence_transformer()
            second = model_cache.get_sentence_transformer()

            assert first is second
            assert m_st.call_count == 1

    def test_a_missing_dependency_returns_none_instead_of_raising(self):
        """Callers keep their degraded path; an optional extra must not raise."""
        with patch.dict("sys.modules", {"sentence_transformers": None}):
            with patch(
                "builtins.__import__", side_effect=ImportError("no sentence_transformers")
            ):
                model_cache.clear_model_cache()
                assert model_cache.get_cross_encoder() is None

    def test_a_failed_load_is_not_cached(self):
        """Installing the extra mid-session must start working without a restart."""
        with patch("sentence_transformers.CrossEncoder") as m_ce:
            m_ce.side_effect = [RuntimeError("boom"), MagicMock()]

            assert model_cache.get_cross_encoder() is None
            assert model_cache.get_cross_encoder() is not None


# ── settings.rerank, which has no schema ────────────────────────────────────


class TestRerankConfig:
    def test_disabled_by_default(self):
        assert rerank_config({})["enabled"] is False

    def test_defaults_are_usable(self):
        cfg = rerank_config({"rerank": {"enabled": True}})

        assert cfg["enabled"] is True
        assert cfg["top_n"] == 20
        assert cfg["max_length"] == 512
        assert cfg["model"]

    def test_a_non_dict_rerank_section_is_ignored(self):
        """`"rerank": true` is a plausible typo; it must not crash a run."""
        assert rerank_config({"rerank": True})["enabled"] is False

    def test_unusable_numbers_fall_back_to_defaults(self):
        cfg = rerank_config(
            {"rerank": {"enabled": True, "top_n": "vinte", "max_length": -3}}
        )

        assert cfg["top_n"] == 20
        assert cfg["max_length"] == 512

    def test_an_explicit_top_n_is_honoured(self):
        assert rerank_config({"rerank": {"top_n": 30}})["top_n"] == 30


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
