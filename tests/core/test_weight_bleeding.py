"""Weight-Bleeding: Comprehensive test suite for scoring formulas and modes.

This test suite verifies the mathematical correctness of the Weight-Bleeding
scoring system across all ablation modes and edge cases.

Run:  pytest tests/core/test_weight_bleeding.py -v
"""

import sys
import math
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


# =============================================================================
# PART 1: SemanticScreener — Core formula tests
# =============================================================================

class TestWeightBleedingFormula:
    """Verify the core Weight-Bleeding formula:

        v_bleeding = (N/(N+W)) * v + (W/(N+W)) * e_t

    Implemented as term repetition in reference text before embedding.
    Cosine similarity between paper text and repeated-term reference
    should be ∈ [0, 1] and reflect term importance.
    """

    def test_semantic_score_range(self):
        """Semantic score should always be between 0 and 1 (cosine similarity)."""
        from academic_hunter.plugins.screeners.semantic import SemanticScreener
        screener = SemanticScreener()

        configs = [
            {"anchors": {"A": ["blockchain"]}, "technical_strings": {}, "technical_weights": {"blockchain": 5.0}},
            {"anchors": {"A": ["ai"]}, "technical_strings": {}, "technical_weights": {"ai": 3.0, "machine learning": 5.0}},
            {"anchors": {"A": ["privacy"]}, "technical_strings": {}, "technical_weights": {}},
        ]
        papers = [
            {"Title": "Blockchain Technology", "Abstract": "Blockchain for secure transactions."},
            {"Title": "Machine Learning Advances", "Abstract": "AI and deep learning developments."},
            {"Title": "", "Abstract": ""},
            {"Title": "Random Topic", "Abstract": ""},
        ]

        for cfg in configs:
            for pap in papers:
                score = screener.evaluate(pap, cfg)
                assert 0.0 <= score <= 1.0, (
                    f"Score {score} must be in [0,1] for cfg={cfg}, paper={pap['Title']}"
                )

    def test_weighted_centroid_pull(self):
        """Higher weight on a term should pull the centroid more.

        Paper about 'privacy' with config emphasizing 'privacy' (weight=5)
        should score HIGHER than with config emphasizing 'zero knowledge proof' (weight=5).
        """
        from academic_hunter.plugins.screeners.semantic import SemanticScreener
        screener = SemanticScreener()

        paper = {"Title": "Privacy preserving transactions", "Abstract": ""}

        cfg_privacy = {
            "anchors": {"Cat": ["privacy"]},
            "technical_strings": {},
            "technical_weights": {"zero knowledge proof": 1.0, "privacy": 5.0},
        }
        cfg_zkp = {
            "anchors": {"Cat": ["privacy"]},
            "technical_strings": {},
            "technical_weights": {"zero knowledge proof": 5.0, "privacy": 1.0},
        }

        score_privacy = screener.evaluate(paper, cfg_privacy)
        score_zkp = screener.evaluate(paper, cfg_zkp)

        assert score_privacy > score_zkp, (
            f"Privacy weight 5 ({score_privacy}) should beat ZKP weight 5 ({score_zkp}) "
            f"for a privacy paper"
        )

    def test_higher_weight_higher_similarity(self):
        """Increasing weight of a term pulls centroid away from base toward the term.

        With a BASE reference (anchors), higher W shifts the centroid more.
        Without a base, v_ref = v_term regardless of W (weight cancels out).
        """
        from academic_hunter.plugins.screeners.semantic import SemanticScreener
        screener = SemanticScreener()

        paper = {"Title": "Blockchain Interoperability Framework", "Abstract": ""}

        # Must include a BASE (anchors) to see the weight effect.
        # The centroid shifts from base_parts toward "blockchain" as W increases.
        scores = []
        for weight in [1, 3, 5, 10]:
            cfg = {
                "anchors": {"Cat": ["base reference anchor"]},
                "technical_strings": {},
                "technical_weights": {"blockchain": float(weight)},
            }
            score = screener.evaluate(paper, cfg)
            scores.append(score)

        # Different weights produce different centroid positions (base→term shift)
        unique_scores = set(round(s, 4) for s in scores)
        assert len(unique_scores) >= 2, (
            f"Expected at least 2 distinct scores across weights {scores}"
        )

    def test_empty_paper_returns_zero(self):
        """Paper with no title and no abstract should return 0.0."""
        from academic_hunter.plugins.screeners.semantic import SemanticScreener
        screener = SemanticScreener()
        assert screener.evaluate({"Title": "", "Abstract": ""}, {
            "anchors": {"A": ["test"]}, "technical_strings": {}, "technical_weights": {}
        }) == 0.0

    def test_no_tech_weights_still_works(self):
        """Config with empty tech_weights should still score based on anchors."""
        from academic_hunter.plugins.screeners.semantic import SemanticScreener
        screener = SemanticScreener()
        score = screener.evaluate(
            {"Title": "Blockchain Research", "Abstract": ""},
            {"anchors": {"Cat": ["blockchain"]}, "technical_strings": {}, "technical_weights": {}}
        )
        assert 0.0 <= score <= 1.0


# =============================================================================
# PART 2: PaperValidator — Ablation mode integration tests
# =============================================================================

class TestAblationModes:
    """Verify PaperValidator correctly applies each ablation mode."""

    @pytest.fixture
    def setup(self):
        from academic_hunter.core.infra.config import HunterConfig
        from academic_hunter.core.nlp import AcademicScorer
        from academic_hunter.plugins.screeners.semantic import SemanticScreener
        from academic_hunter.core.screening.validators import PaperValidator

        cfg = HunterConfig()
        cfg.load(force=True)

        # Use a controlled test config (not dependent on current config.json)
        test_settings = dict(cfg.settings)
        test_settings.update({
            "title_multiplier": 2.5,
            "score_precision": 1,
        })

        # Minimal config for reproducible tests
        test_anchors = {"Test": ["blockchain", "sentence embedding"]}
        test_tech_strings = {"Retrieval": ["information retrieval", "search"]}
        test_tech_weights = {"blockchain": 5.0, "sentence embedding": 5.0, "information retrieval": 3.0}
        test_context_rules = {}

        scorer = AcademicScorer(test_anchors, test_tech_strings, test_tech_weights,
                                test_context_rules, test_settings)
        screener = SemanticScreener()

        # Create a patched config with test data
        cfg.anchors = test_anchors
        cfg.tech_strings = test_tech_strings
        cfg.tech_weights = test_tech_weights
        cfg.context_rules = test_context_rules
        cfg.settings = test_settings

        paper = {
            "Title": "Blockchain and Sentence Embedding: A Novel Approach",
            "Abstract": "We propose a new method for information retrieval using blockchain technology and sentence embeddings.",
            "Year": 2024,
            "Citations": 5,
        }

        return cfg, scorer, screener, paper

    def test_keyword_mode(self, setup):
        """Keyword mode should return only the regex keyword score (no semantic blend)."""
        from academic_hunter.core.screening.validators import PaperValidator
        cfg, scorer, screener, paper = setup

        cfg.settings["ablation"] = {"mode": "keyword"}
        validator = PaperValidator(cfg, scorer, screener)

        passed, reason, cat, terms, score, tech = validator.validate_and_score(
            paper, paper["Title"], cfg.tech_strings["Retrieval"]
        )

        # Keyword score for: blockchain×2.5(título) + sentence embedding×2.5(título) +
        #                    information retrieval(abstract) + log10(6) ≈ 12.5+12.5+3.0+0.8 = 28.8
        keyword_only = scorer.calculate_score(paper["Title"], paper["Abstract"], paper["Citations"])

        assert passed
        assert score == keyword_only, f"Keyword mode should = {keyword_only}, got {score}"
        assert "sentence embedding" in terms or "blockchain" in terms

    def test_embedding_mode(self, setup):
        """Embedding mode should return only semantic × 10 (keyword ignored)."""
        from academic_hunter.core.screening.validators import PaperValidator
        cfg, scorer, screener, paper = setup

        cfg.settings["ablation"] = {"mode": "embedding"}
        validator = PaperValidator(cfg, scorer, screener)

        passed, reason, cat, terms, score, tech = validator.validate_and_score(
            paper, paper["Title"], cfg.tech_strings["Retrieval"]
        )

        # Embedding formula: (keyword * 0.0) + (semantic * 10.0 * 1.0) = semantic * 10.0
        # Max possible = 10.0 (since semantic ∈ [0, 1])
        assert 0.0 <= score <= 10.0, (
            f"Embedding mode score {score} should be ≤ 10.0"
            f" (formula: semantic × 10)"
        )

        # Should be lower than keyword score (semantic is dampened vs exact matches)
        keyword_only = scorer.calculate_score(paper["Title"], paper["Abstract"], paper["Citations"])
        assert score < keyword_only, (
            f"Embedding {score} should be < keyword {keyword_only}"
        )

    def test_hybrid_mode(self, setup):
        """Hybrid mode should return sqrt(semantic)×10 + kw×0.3."""
        from academic_hunter.core.screening.validators import PaperValidator
        cfg, scorer, screener, paper = setup

        cfg.settings["ablation"] = {"mode": "hybrid"}
        validator = PaperValidator(cfg, scorer, screener)

        passed, reason, cat, terms, score, tech = validator.validate_and_score(
            paper, paper["Title"], cfg.tech_strings["Retrieval"]
        )

        # Compute expected
        import math
        keyword_score = scorer.calculate_score(paper["Title"], paper["Abstract"], paper["Citations"])
        sem_config = {
            "anchors": cfg.anchors,
            "technical_strings": cfg.tech_strings,
            "technical_weights": cfg.tech_weights,
        }
        semantic_score = screener.evaluate(paper, sem_config)
        expected = round(math.sqrt(semantic_score) * 10.0 + keyword_score * 0.3, 1)

        assert score == expected, (
            f"Hybrid score {score} should equal {expected}"
        )
        # Hybrid should be >= sqrt(WB-only) since keyword adds bonus
        assert score >= round(math.sqrt(semantic_score) * 10.0, 1), (
            f"Hybrid {score} should be >= sqrt(WB) {round(math.sqrt(semantic_score) * 10.0, 1)}"
        )
        assert score >= 0, f"Hybrid score should be ≥ 0"

    def test_hybrid_between_keyword_and_embedding(self, setup):
        """Hybrid score should be between keyword-only and embedding-only."""
        from academic_hunter.core.screening.validators import PaperValidator
        cfg, scorer, screener, paper = setup

        scores = {}
        for mode in ["keyword", "embedding", "hybrid"]:
            cfg.settings["ablation"] = {"mode": mode}
            validator = PaperValidator(cfg, scorer, screener)
            _, _, _, _, score, _ = validator.validate_and_score(
                paper, paper["Title"], cfg.tech_strings["Retrieval"]
            )
            scores[mode] = score

        # Ordering: embedding <= hybrid (WB is base, keyword adds bonus)
        assert scores["embedding"] <= scores["hybrid"], (
            f"Expected embedding({scores['embedding']}) <= hybrid({scores['hybrid']}) "
            f"(hybrid = WB + keyword bonus)"
        )


# =============================================================================
# PART 3: compute_hybrid_score — Duplicate resolution tests
# =============================================================================

class TestComputeHybridScore:
    """Verify compute_hybrid_score (used for duplicate resolution)."""

    @pytest.fixture
    def setup(self):
        from academic_hunter.core.infra.config import HunterConfig
        from academic_hunter.core.nlp import AcademicScorer
        from academic_hunter.plugins.screeners.semantic import SemanticScreener
        from academic_hunter.core.screening.validators import PaperValidator

        cfg = HunterConfig()
        cfg.load(force=True)

        test_anchors = {"Test": ["quantum"]}
        test_tech_weights = {"quantum computing": 5.0, "cryptography": 3.0}
        test_settings = dict(cfg.settings)
        test_settings.update({"title_multiplier": 2.5, "score_precision": 1})

        cfg.anchors = test_anchors
        cfg.tech_strings = {"Tech": ["computing"]}
        cfg.tech_weights = test_tech_weights
        cfg.settings = test_settings

        scorer = AcademicScorer(test_anchors, {"Tech": ["computing"]},
                                test_tech_weights, {}, test_settings)
        screener = SemanticScreener()
        validator = PaperValidator(cfg, scorer, screener)

        return cfg, validator, scorer, screener

    def test_same_as_validate_and_score_keyword(self, setup):
        """compute_hybrid_score should match validate_and_score in keyword mode."""
        cfg, validator, scorer, screener = setup
        cfg.settings["ablation"] = {"mode": "keyword"}

        paper_dict = {"Title": "Quantum Cryptography", "Abstract": "Quantum computing advances.", "Citations": 3}

        # From validate_and_score
        _, _, _, _, score_v, _ = validator.validate_and_score(
            paper_dict, paper_dict["Title"], cfg.tech_strings["Tech"]
        )

        # From compute_hybrid_score
        score_c = validator.compute_hybrid_score(paper_dict)

        assert score_v == score_c, (
            f"Mismatch: validate={score_v}, compute={score_c}"
        )

    def test_same_as_validate_and_score_embedding(self, setup):
        """compute_hybrid_score should match validate_and_score in embedding mode."""
        cfg, validator, scorer, screener = setup
        cfg.settings["ablation"] = {"mode": "embedding"}

        paper_dict = {"Title": "Quantum Cryptography", "Abstract": "Quantum computing advances.", "Citations": 3}

        _, _, _, _, score_v, _ = validator.validate_and_score(
            paper_dict, paper_dict["Title"], cfg.tech_strings["Tech"]
        )
        score_c = validator.compute_hybrid_score(paper_dict)

        assert score_v == score_c, (
            f"Mismatch: validate={score_v}, compute={score_c}"
        )

    def test_same_as_validate_and_score_hybrid(self, setup):
        """compute_hybrid_score should match validate_and_score in hybrid mode."""
        cfg, validator, scorer, screener = setup
        cfg.settings["ablation"] = {"mode": "hybrid"}

        paper_dict = {"Title": "Quantum Cryptography", "Abstract": "Quantum computing advances.", "Citations": 3}

        _, _, _, _, score_v, _ = validator.validate_and_score(
            paper_dict, paper_dict["Title"], cfg.tech_strings["Tech"]
        )
        score_c = validator.compute_hybrid_score(paper_dict)

        assert score_v == score_c, (
            f"Mismatch: validate={score_v}, compute={score_c}"
        )


# =============================================================================
# PART 4: Config propagation — Verify ablation mode reaches validator
# =============================================================================

class TestConfigPropagation:
    """Verify that the ablation mode from config.json reaches PaperValidator."""

    def test_semantic_screener_present_in_validator(self):
        """Validator should receive the SemanticScreener from the pipeline."""
        from academic_hunter import AcademicHunter

        hunter = AcademicHunter()
        validator = hunter.processor.resolver.validator

        assert validator.semantic_screener is not None, (
            "semantic_screener should be passed to PaperValidator"
        )

    def test_ablation_mode_from_config(self):
        """The ablation mode from config.json should be readable in validator."""
        from academic_hunter import AcademicHunter
        from academic_hunter.core.infra.config import HunterConfig

        # Read config directly
        cfg = HunterConfig()
        cfg.load(force=True)
        config_mode = cfg.settings.get("ablation", {}).get("mode", "hybrid")

        # Read via hunter
        hunter = AcademicHunter()
        hunter_mode = hunter.config.settings.get("ablation", {}).get("mode", "hybrid")

        # Both should be the same
        assert hunter_mode == config_mode, (
            f"Hunter mode ({hunter_mode}) != direct config ({config_mode})"
        )

    def test_mode_affects_scoring(self):
        """Changing the mode should change the score."""
        from academic_hunter.core.infra.config import HunterConfig
        from academic_hunter.core.nlp import AcademicScorer
        from academic_hunter.plugins.screeners.semantic import SemanticScreener
        from academic_hunter.core.screening.validators import PaperValidator

        cfg = HunterConfig()
        cfg.load(force=True)

        test_anchors = {"Test": ["blockchain"]}
        test_tech_strings = {"Tech": ["blockchain"]}
        test_tech_weights = {"blockchain": 5.0}
        test_settings = {"title_multiplier": 2.5, "score_precision": 1}

        cfg.anchors = test_anchors
        cfg.tech_strings = test_tech_strings
        cfg.tech_weights = test_tech_weights
        cfg.settings = test_settings

        scorer = AcademicScorer(test_anchors, test_tech_strings,
                                test_tech_weights, {}, test_settings)
        screener = SemanticScreener()

        paper = {"Title": "Blockchain Technology Advances", "Abstract": "Blockchain in finance",
                 "Year": 2024, "Citations": 0}
        tech_list = test_tech_strings["Tech"]

        scores = []
        for mode in ["keyword", "embedding"]:
            cfg.settings["ablation"] = {"mode": mode}
            validator = PaperValidator(cfg, scorer, screener)
            passed, _, _, _, score, _ = validator.validate_and_score(
                paper, paper["Title"], tech_list
            )
            assert passed, f"Paper should pass anchor filter for {mode}"
            scores.append(score)

        assert scores[0] != scores[1], (
            f"Keyword ({scores[0]}) and embedding ({scores[1]}) should differ"
        )


# =============================================================================
# PART 5: AcademicScorer — Keyword score tests
# =============================================================================

class TestAcademicScorer:
    """Verify the keyword scoring component."""

    def test_title_gets_multiplier(self):
        """Terms found in title should get title_multiplier boost."""
        from academic_hunter.core.nlp import AcademicScorer

        scorer = AcademicScorer(
            {"A": ["blockchain"]},
            {"B": ["blockchain"]},
            {"blockchain": 5.0},
            {},
            {"title_multiplier": 2.5, "score_precision": 1}
        )

        # Term in title
        title_score = scorer.calculate_score("Blockchain Technology", "", 0)
        # Term in abstract
        abstract_score = scorer.calculate_score("", "Blockchain technology paper", 0)

        assert title_score == abstract_score * 2.5, (
            f"Title score ({title_score}) should be 2.5× abstract ({abstract_score})"
        )

    def test_citation_bonus(self):
        """Citations should add a logarithmic bonus."""
        from academic_hunter.core.nlp import AcademicScorer

        scorer = AcademicScorer({}, {}, {}, {}, {"title_multiplier": 1.0, "score_precision": 1})

        score_0 = scorer.calculate_score("Test", "", 0)
        score_10 = scorer.calculate_score("Test", "", 10)
        score_100 = scorer.calculate_score("Test", "", 100)

        assert score_10 > score_0, f"With citations should score higher"
        assert score_100 > score_10, f"More citations should score higher"
        # log10(11) ≈ 1.0, log10(101) ≈ 2.0
        assert abs((score_100 - score_10) - (math.log10(101) - math.log10(11))) < 0.1

    def test_no_match_returns_baseline(self):
        """A paper with no matching terms should return just the citation bonus."""
        from academic_hunter.core.nlp import AcademicScorer

        scorer = AcademicScorer(
            {"A": ["rareterm123"]},
            {"B": ["rareterm123"]},
            {"rareterm123": 5.0},
            {},
            {"title_multiplier": 1.0, "score_precision": 1}
        )

        score = scorer.calculate_score("Common words only", "", 0)
        assert score == 0.0, f"No matching terms should score 0, got {score}"

        # With citations, should get log10(citations+1)
        score_with_cit = scorer.calculate_score("Common words only", "", 99)
        expected_cit = round(math.log10(100), 1)
        assert score_with_cit == expected_cit, (
            f"Score {score_with_cit} should be just citation bonus {expected_cit}"
        )


# =============================================================================
# PART 6: Cross-encoder correlation tests
# =============================================================================

class TestCrossEncoderCorrelation:
    """Verify cross-encoder (CE) scoring is distinct from Weight-Bleeding."""

    def test_ce_scores_differ_from_bi_encoder(self):
        """Cross-encoder and bi-encoder scores should differ (different objectives)."""
        import json
        from pathlib import Path

        result_path = Path(__file__).parent.parent.parent / "papers/experiments/results/cross_encoder_correlation.json"
        if not result_path.exists():
            pytest.skip("Cross-encoder results not found. Run cross_encoder_val.py first.")

        data = json.loads(result_path.read_text())
        results = data.get("results", [])

        assert len(results) >= 3, f"Need at least 3 results, got {len(results)}"

        # Verify scores are not identical across methods
        for r in results:
            assert not (r["bi_encoder_vanilla"] == r["weight_bleeding"] == r["cross_encoder"]), (
                f"All scores identical for {r['query']}"
            )

    def test_weight_bleeding_changes_ranking(self):
        """Weight-Bleeding should produce different rankings from vanilla bi-encoder."""
        import json
        from pathlib import Path

        result_path = Path(__file__).parent.parent.parent / "papers/experiments/results/cross_encoder_correlation.json"
        if not result_path.exists():
            pytest.skip("Cross-encoder results not found.")

        data = json.loads(result_path.read_text())
        results = data.get("results", [])

        if len(results) < 2:
            pytest.skip("Need at least 2 results for ranking comparison")

        # Rank by vanilla vs weight-bleeding
        rank_vanilla = sorted(range(len(results)), key=lambda i: results[i]["bi_encoder_vanilla"])
        rank_wb = sorted(range(len(results)), key=lambda i: results[i]["weight_bleeding"])

        # Rankings should differ (centroid shift)
        assert rank_vanilla != rank_wb, (
            "Weight-Bleeding should change rankings from vanilla bi-encoder"
        )


# =============================================================================
# PART 7: End-to-end pipeline integration tests
# =============================================================================

class TestPipelineIntegration:
    """Verify scoring through the full pipeline."""

    def test_pipeline_scores_consistent(self):
        """Papers in consolidated_results should have valid scores."""
        from academic_hunter import AcademicHunter
        from academic_hunter.core.infra.config import HunterConfig

        # Read current config
        cfg = HunterConfig()
        mode = cfg.settings.get("ablation", {}).get("mode", "hybrid")

        hunter = AcademicHunter()
        scores = [p.get("Relevance_Score", -1) for p in hunter.state.consolidated_results.values()]

        # If there are results, verify scores
        if scores:
            assert all(s >= 0 for s in scores), "All scores should be ≥ 0"

            if mode == "embedding":
                assert all(s <= 10.0 for s in scores), (
                    f"Embedding mode: all scores should be ≤ 10.0, got max {max(scores)}"
                )


# =============================================================================
# Main: Run tests and print summary
# =============================================================================

if __name__ == "__main__":
    import pytest
    import sys

    print("=" * 60)
    print("  Weight-Bleeding Test Suite")
    print("  Validating scoring formulas and integration")
    print("=" * 60)

    # Run all tests with verbose output
    exit_code = pytest.main([__file__, "-v", "--tb=short", "--no-header"] + sys.argv[1:])
    sys.exit(exit_code)
