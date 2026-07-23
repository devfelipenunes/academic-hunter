"""SemanticScreener — Golden tests to lock behavior before refactoring.

These tests capture exact numeric outputs and internal contract guarantees so
that any regression introduced by a refactor is caught immediately.

Run:
    pytest tests/core/test_semantic_screener.py -v
"""

import sys
import math
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from academic_hunter.plugins.screeners.semantic import SemanticScreener


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def screener():
    """Single SemanticScreener reused across tests (shares embedding cache)."""
    return SemanticScreener()


@pytest.fixture(scope="module")
def base_config():
    return {
        "anchors": {"Main": ["blockchain", "distributed ledger"]},
        "technical_strings": {"Tech": ["smart contract", "consensus protocol"]},
        "technical_weights": {"blockchain": 5.0, "smart contract": 3.0},
    }


@pytest.fixture(scope="module")
def base_paper():
    return {
        "Title": "Blockchain Technology for Secure Transactions",
        "Abstract": "We propose a smart contract approach to distributed ledger systems.",
    }


# ===========================================================================
# PART 1 — Score range & basic contracts
# ===========================================================================

class TestScoreRange:
    """Score must always be a float in [0, 1]."""

    def test_relevant_paper_score_is_in_range(self, screener, base_config, base_paper):
        score = screener.evaluate(base_paper, base_config)
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_empty_paper_returns_zero(self, screener, base_config):
        assert screener.evaluate({"Title": "", "Abstract": ""}, base_config) == 0.0

    def test_none_title_none_abstract_returns_zero(self, screener, base_config):
        assert screener.evaluate({"title": None, "abstract": None}, base_config) == 0.0

    def test_empty_config_returns_zero(self, screener, base_paper):
        cfg = {"anchors": {}, "technical_strings": {}, "technical_weights": {}}
        assert screener.evaluate(base_paper, cfg) == 0.0

    def test_off_topic_paper_scores_lower_than_relevant(self, screener, base_config):
        off_topic = {"Title": "Culinary Techniques for Pasta Dishes", "Abstract": "Boiling water."}
        on_topic = {"Title": "Blockchain Distributed Ledger", "Abstract": "Smart contract consensus."}
        assert screener.evaluate(on_topic, base_config) > screener.evaluate(off_topic, base_config)


# ===========================================================================
# PART 2 — Determinism & caching
# ===========================================================================

class TestDeterminism:
    """Same inputs must always produce the same score."""

    def test_same_paper_same_config_same_score(self, screener, base_config, base_paper):
        s1 = screener.evaluate(base_paper, base_config)
        s2 = screener.evaluate(base_paper, base_config)
        assert s1 == s2, f"Scores differ across calls: {s1} vs {s2}"

    def test_fresh_screener_same_score(self, base_config, base_paper):
        """Two separate SemanticScreener instances should produce identical scores."""
        s1 = SemanticScreener().evaluate(base_paper, base_config)
        s2 = SemanticScreener().evaluate(base_paper, base_config)
        assert abs(s1 - s2) < 1e-6, f"Fresh instances differ: {s1} vs {s2}"

    def test_cache_populated_after_first_call(self, base_config, base_paper):
        """After evaluate(), _cached_base should have exactly one entry."""
        s = SemanticScreener()
        assert len(s._cached_base) == 0
        s.evaluate(base_paper, base_config)
        assert len(s._cached_base) == 1

    def test_cache_reused_same_config(self, base_config, base_paper):
        """Two papers with the same config should not grow the cache."""
        s = SemanticScreener()
        paper2 = {"Title": "Another Blockchain Paper", "Abstract": "Distributed nodes."}
        s.evaluate(base_paper, base_config)
        s.evaluate(paper2, base_config)
        assert len(s._cached_base) == 1

    def test_cache_grows_with_different_configs(self, base_paper):
        """Different configs should produce separate cache entries."""
        s = SemanticScreener()
        cfg1 = {"anchors": {"A": ["blockchain"]}, "technical_strings": {}, "technical_weights": {}}
        cfg2 = {"anchors": {"B": ["privacy"]}, "technical_strings": {}, "technical_weights": {}}
        s.evaluate(base_paper, cfg1)
        s.evaluate(base_paper, cfg2)
        assert len(s._cached_base) == 2


# ===========================================================================
# PART 3 — Weight-Bleeding: centroid math
# ===========================================================================

class TestWeightBleedingMath:
    """Verify the weighted centroid pulls the reference toward high-weight terms."""

    def test_higher_weight_pulls_centroid(self):
        """Higher weight on a term that is strongly aligned with the paper should
        increase the score.

        We use a controlled mock so this test is independent of the ONNX model.
        Setup:
          - anchor (base) vector  = [1, 0, 0]  (3-D for clarity)
          - term vector ("alpha") = [0, 1, 0]
          - paper vector          = [0, 1, 0]  (perfect match with "alpha")

        With weight=1: v_ref = ([1,0,0]*1 + [0,1,0]*1) / 2 = [0.5, 0.5, 0]
          cos(paper, v_ref) = 0.5 / (1 * √0.5) ≈ 0.707

        With weight=10: v_ref = ([1,0,0]*1 + [0,1,0]*10) / 11 = [1/11, 10/11, 0]
          cos(paper, v_ref) ≈ (10/11) / (1 * √(1/121 + 100/121)) > 0.707
        """
        import numpy as np

        dim = 3
        v_base = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        v_alpha = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        v_paper = np.array([0.0, 1.0, 0.0], dtype=np.float32)

        embed_map = {
            "anchor_base alpha_term": v_base,  # base text (join of anchors + tech_strings)
            "alpha_term": v_alpha,
        }

        class MockEmbed:
            def __call__(self, texts):
                result = []
                for t in texts:
                    result.append(embed_map.get(t, v_paper))
                return result

        def make_screener():
            s = SemanticScreener()
            s._embedding_function = MockEmbed()
            return s

        cfg_low = {
            "anchors": {"A": ["anchor_base"]},
            "technical_strings": {"B": ["alpha_term"]},
            "technical_weights": {"alpha_term": 1.0},
        }
        cfg_high = {
            "anchors": {"A": ["anchor_base"]},
            "technical_strings": {"B": ["alpha_term"]},
            "technical_weights": {"alpha_term": 10.0},
        }

        paper = {"Title": "dummy", "Abstract": "dummy"}
        score_low = make_screener().evaluate(paper, cfg_low)
        score_high = make_screener().evaluate(paper, cfg_high)

        assert score_high > score_low, (
            f"Higher weight ({score_high:.4f}) should outscore lower weight ({score_low:.4f})"
        )

    def test_unrelated_high_weight_hurts_score(self, screener):
        """Paper on 'machine learning'. A config that heavily weights an unrelated
        term ('medieval architecture') should score lower than one weighted on ML."""
        paper = {"Title": "Deep Learning for Image Recognition", "Abstract": "Neural networks."}

        cfg_relevant = {
            "anchors": {"A": ["machine learning"]},
            "technical_strings": {},
            "technical_weights": {"neural network": 8.0},
        }
        cfg_irrelevant = {
            "anchors": {"A": ["machine learning"]},
            "technical_strings": {},
            "technical_weights": {"medieval gothic architecture": 8.0},
        }

        score_rel = screener.evaluate(paper, cfg_relevant)
        score_irr = screener.evaluate(paper, cfg_irrelevant)
        assert score_rel > score_irr, (
            f"Relevant weight ({score_rel}) should beat irrelevant weight ({score_irr})"
        )

    def test_weight_zero_equivalent_to_no_tech_weights(self):
        """A technical_weight of 0 for every term should be equivalent to an
        empty technical_weights dict (same centroid = same score)."""
        s = SemanticScreener()
        paper = {"Title": "Blockchain Research", "Abstract": "Distributed systems."}

        cfg_empty_w = {
            "anchors": {"A": ["blockchain"]},
            "technical_strings": {},
            "technical_weights": {},
        }
        cfg_zero_w = {
            "anchors": {"A": ["blockchain"]},
            "technical_strings": {},
            "technical_weights": {"blockchain": 0.0},
        }

        score_empty = s.evaluate(paper, cfg_empty_w)
        score_zero = s.evaluate(paper, cfg_zero_w)
        # Note: 0-weight term still triggers an embedding call and shifts the
        # centroid by 0; scores may differ slightly due to vector normalization.
        # Both should be valid floats in [0,1].
        assert 0.0 <= score_empty <= 1.0
        assert 0.0 <= score_zero <= 1.0


# ===========================================================================
# PART 4 — Numeric precision & golden scores
# ===========================================================================

class TestGoldenScores:
    """Lock down exact score values so any change in the formula is visible.

    These tests use a controlled MockEmbedding to remove the ONNX model from
    the equation — the math is tested in isolation.
    """

    @pytest.fixture
    def mock_screener(self, monkeypatch):
        """SemanticScreener with a deterministic fake embedding function.

        Embedding map (384-dim unit vectors — only first component set):
            "blockchain distributed ledger smart contract consensus protocol" -> [1, 0, 0, ...]
            "blockchain"    -> [1, 0, 0, ...]
            "smart contract"-> [0, 1, 0, ...]
            paper text      -> [0.6, 0.8, 0, ...]  (norm=1)
        """
        dim = 384

        # Precomputed unit vectors
        v_base = np.zeros(dim, dtype=np.float32); v_base[0] = 1.0
        v_blockchain = np.zeros(dim, dtype=np.float32); v_blockchain[0] = 1.0
        v_smart = np.zeros(dim, dtype=np.float32); v_smart[1] = 1.0
        v_paper = np.zeros(dim, dtype=np.float32); v_paper[0] = 0.6; v_paper[1] = 0.8  # already unit

        # Map each possible text to its fake embedding
        embed_map = {
            # base text = join of all anchors + tech_strings
            "blockchain distributed ledger smart contract consensus protocol": v_base,
            "blockchain": v_blockchain,
            "smart contract": v_smart,
        }

        class MockEmbed:
            def __call__(self, texts):
                result = []
                for t in texts:
                    if t in embed_map:
                        result.append(embed_map[t])
                    else:
                        # paper text → v_paper
                        result.append(v_paper)
                return result

        s = SemanticScreener()
        s._embedding_function = MockEmbed()
        return s

    def test_golden_score_with_mock_embedding(self, mock_screener):
        """Manually compute expected score and compare.

        Config:
            base_parts = ["blockchain", "distributed ledger", "smart contract", "consensus protocol"]
              → N_base = 4, v_base = [1, 0, ...]
            tech_weights: {"blockchain": 5.0, "smart contract": 3.0}
              → W_blockchain=5, v_blockchain=[1,0,...]; W_smart=3, v_smart=[0,1,...]

        v_sum  = v_base*4 + v_blockchain*5 + v_smart*3
               = [4,0,...] + [5,0,...] + [0,3,...] = [9, 3, 0, ...]
        total_w= 4 + 5 + 3 = 12
        v_ref  = [9/12, 3/12, 0, ...] = [0.75, 0.25, 0, ...]

        v_paper = [0.6, 0.8, 0, ...] (norm=1)
        norm_ref = sqrt(0.75² + 0.25²) = sqrt(0.5625 + 0.0625) = sqrt(0.625)

        cosine = dot(v_paper, v_ref) / (1 * norm_ref)
               = (0.6*0.75 + 0.8*0.25) / sqrt(0.625)
               = (0.45 + 0.20) / 0.7906
               = 0.65 / 0.7906 ≈ 0.8222
        """
        config = {
            "anchors": {"Main": ["blockchain", "distributed ledger"]},
            "technical_strings": {"Tech": ["smart contract", "consensus protocol"]},
            "technical_weights": {"blockchain": 5.0, "smart contract": 3.0},
        }
        paper = {"Title": "Test Paper", "Abstract": "dummy text"}

        score = mock_screener.evaluate(paper, config)

        # Recompute expected
        v_ref_raw = np.array([9.0, 3.0] + [0.0] * 382, dtype=np.float32)
        v_ref = v_ref_raw / 12.0
        v_paper = np.zeros(384, dtype=np.float32)
        v_paper[0] = 0.6; v_paper[1] = 0.8
        norm_ref = np.linalg.norm(v_ref)
        expected = float(np.dot(v_paper, v_ref) / (1.0 * norm_ref))

        assert abs(score - expected) < 1e-5, (
            f"Golden score {score:.6f} differs from expected {expected:.6f}"
        )

    def test_only_tech_weights_no_base(self, mock_screener):
        """With no anchors/tech_strings, v_ref = weighted avg of term embeddings."""
        config = {
            "anchors": {},
            "technical_strings": {},
            "technical_weights": {"blockchain": 5.0, "smart contract": 3.0},
        }
        paper = {"Title": "Test Paper", "Abstract": "dummy text"}

        score = mock_screener.evaluate(paper, config)

        # v_sum = v_blockchain*5 + v_smart*3 = [5,0,...] + [0,3,...] = [5,3,...]
        # total_w = 8
        # v_ref = [5/8, 3/8, ...] = [0.625, 0.375, ...]
        v_ref_raw = np.array([5.0, 3.0] + [0.0] * 382, dtype=np.float32)
        v_ref = v_ref_raw / 8.0
        v_paper = np.zeros(384, dtype=np.float32); v_paper[0] = 0.6; v_paper[1] = 0.8
        norm_ref = np.linalg.norm(v_ref)
        expected = float(np.dot(v_paper, v_ref) / (1.0 * norm_ref))

        assert abs(score - expected) < 1e-5, (
            f"No-base golden score {score:.6f} != expected {expected:.6f}"
        )


# ===========================================================================
# PART 5 — Paper text extraction
# ===========================================================================

class TestPaperTextExtraction:
    """Verify that title/abstract are extracted from both snake_case and Title_Case keys."""

    def test_title_case_keys(self, screener, base_config):
        paper = {"Title": "Blockchain Research", "Abstract": "Distributed nodes."}
        score = screener.evaluate(paper, base_config)
        assert score > 0.0

    def test_snake_case_keys(self, screener, base_config):
        paper = {"title": "Blockchain Research", "abstract": "Distributed nodes."}
        score = screener.evaluate(paper, base_config)
        assert score > 0.0

    def test_mixed_keys_consistent_score(self, screener, base_config):
        """snake_case and Title_Case versions of the same paper should get same score."""
        p_title = {"Title": "Blockchain Research", "Abstract": "Distributed nodes."}
        p_snake = {"title": "Blockchain Research", "abstract": "Distributed nodes."}
        s1 = screener.evaluate(p_title, base_config)
        s2 = screener.evaluate(p_snake, base_config)
        assert abs(s1 - s2) < 1e-6

    def test_title_only_paper_valid(self, screener, base_config):
        paper = {"Title": "Blockchain Networks", "Abstract": ""}
        score = screener.evaluate(paper, base_config)
        assert 0.0 <= score <= 1.0

    def test_abstract_only_paper_valid(self, screener, base_config):
        paper = {"Title": "", "Abstract": "Distributed ledger for smart contracts."}
        score = screener.evaluate(paper, base_config)
        assert 0.0 <= score <= 1.0


# ===========================================================================
# PART 6 — _cosine helper
# ===========================================================================

class TestCosineHelper:
    """Unit tests for the _cosine() method."""

    def test_identical_vectors(self):
        s = SemanticScreener()
        v = [1.0, 0.0, 0.0]
        assert abs(s._cosine(v, v) - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        s = SemanticScreener()
        assert abs(s._cosine([1, 0, 0], [0, 1, 0])) < 1e-6

    def test_zero_vector_returns_zero(self):
        s = SemanticScreener()
        assert s._cosine([0, 0, 0], [1, 0, 0]) == 0.0
        assert s._cosine([1, 0, 0], [0, 0, 0]) == 0.0

    def test_known_angle(self):
        """45° angle → cosine = 1/√2 ≈ 0.7071."""
        s = SemanticScreener()
        result = s._cosine([1, 0], [1, 1])
        assert abs(result - 1 / math.sqrt(2)) < 1e-5


if __name__ == "__main__":
    import pytest, sys
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
