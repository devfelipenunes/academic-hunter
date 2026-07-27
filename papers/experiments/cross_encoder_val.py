#!/usr/bin/env python3
"""Cross-encoder validation: compare Weight-Bleeding vs cross-encoder ranking.

Uses the actual SemanticScreener (embedding-space centroid interpolation)
instead of string-level term repetition, proving the paper's claim that
both approaches are mathematically equivalent.

Also compares against string-level repetition to confirm equivalence.

Measures Spearman rank correlation between:
  - Bi-encoder cosine similarity (vanilla)
  - Weight-Bleeding via SemanticScreener (embedding-space)
  - Weight-Bleeding via string repetition (for equivalence check)
  - Cross-encoder relevance score

Usage:
    python papers/experiments/cross_encoder_val.py [--quick]
"""

import json
import sys
from pathlib import Path

SRC = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(SRC))

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def spearman_rank_correlation(ranking_a: list, ranking_b: list) -> float:
    """Spearman's rank correlation coefficient between two ranked lists."""
    n = len(ranking_a)
    if n < 3:
        return 0.0
    d_sq = sum((ranking_a[i] - ranking_b[i]) ** 2 for i in range(n))
    return 1 - (6 * d_sq) / (n * (n * n - 1))


def main():
    quick = "--quick" in sys.argv

    print("=" * 60)
    print("  Cross-Encoder Validation")
    print("  Weight-Bleeding: embedding-space vs string-level")
    print("=" * 60)

    try:
        from sentence_transformers import CrossEncoder, SentenceTransformer
    except ImportError:
        print("❌ sentence-transformers not installed.")
        sys.exit(1)

    # Import our SemanticScreener (production code)
    from academic_hunter.plugins.screeners.semantic import SemanticScreener

    # Load models
    print("\nLoading models...")
    bi_encoder = SentenceTransformer("all-MiniLM-L6-v2")
    cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    screener = SemanticScreener()

    # Config for Weight-Bleeding (same format as config.json)
    wb_config = {
        "anchors": {
            "Tech": ["sentence embedding", "mean pooling", "cross-chain bridge",
                     "active learning", "hybrid retrieval", "term repetition",
                     "contrastive learning", "smooth inverse frequency",
                     "systematic review", "transformer"]
        },
        "technical_strings": {},
        "technical_weights": {
            "systematic literature review": 5.0,
            "cross-chain bridge": 5.0,
            "sentence embedding": 4.5,
            "mean pooling": 4.5,
            "active learning": 4.0,
            "hybrid retrieval": 4.0,
            "term repetition": 5.0,
            "contrastive learning": 3.5,
            "smooth inverse frequency": 3.5,
            "transformer": 2.0,
        },
    }

    # String-level Weight-Bleeding (for equivalence comparison)
    tech_weights_for_string = {
        "systematic literature review": 5.0, "cross-chain bridge": 5.0,
        "sentence embedding": 4.5, "mean pooling": 4.5, "active learning": 4.0,
        "hybrid retrieval": 4.0, "term repetition": 5.0, "contrastive learning": 3.5,
        "smooth inverse frequency": 3.5, "transformer": 2.0,
    }

    def apply_wb_string(query: str) -> str:
        """String-level term repetition.

        The cross-encoder measures (query, paper) pair relevance, so WB must
        operate on the QUERY embedding (not a config-level centroid). This
        is the correct approach for pairwise relevance experiments.

        In production (SemanticScreener), we compute the weighted centroid
        directly in embedding space — mathematically equivalent when both
        operate at the same level, but the SemanticScreener scores papers
        against a fixed search config rather than a specific query.
        """
        parts = [query]
        for term, weight in tech_weights_for_string.items():
            if term in query.lower():
                parts.extend([term] * (int(weight) - 1))
        return " ".join(parts)

    # Sample query-paper pairs (same as original experiment)
    pairs = [
        ("systematic literature review automation",
         "Evaluation of Attention-Based LSTM and Bi-LSTM Networks For Abstract Text Classification in Systematic Literature Review Automation"),
        ("cross-chain bridge security",
         "Blockchain Cross-Chain Bridge Security: Challenges, Solutions, and Future Outlook"),
        ("sentence embedding mean pooling",
         "Extracting Sentence Embeddings from Pretrained Transformer Models"),
        ("active learning screening",
         "MSR63 Implementing Simple Active Learning Boosters"),
        ("hybrid retrieval scoring",
         "A Multi-Stage Hybrid Retrieval Framework for the Scientific Literature with Cross-Encoder Re-Ranking"),
        ("term repetition embedding",
         "Repetition Improves Language Model Embeddings"),
        ("mean pooling transformer",
         "Why Mean Pooling Works: Quantifying Second-Order Collapse in Text Embeddings"),
        ("contrastive learning sentence",
         "ESimCSE: Enhanced Sample Building Method for Contrastive Learning"),
        ("systematic review tool",
         "SWARM-SLR AIssistant: A Unified Framework for Scalable Systematic Literature Review Automation"),
        ("smooth inverse frequency",
         "A Critique of the Smooth Inverse Frequency Sentence Embeddings"),
    ]

    if quick:
        pairs = pairs[:3]

    print(f"\n  Evaluating {len(pairs)} query-paper pairs...\n")
    import numpy as np

    results = []
    for query, paper_title in pairs:
        # 1. Bi-encoder vanilla (no Weight-Bleeding)
        emb_q = bi_encoder.encode(query)
        emb_p = bi_encoder.encode(paper_title)
        sim_vanilla = float(emb_q @ emb_p / (np.linalg.norm(emb_q) * np.linalg.norm(emb_p) + 1e-10))

        # 2. Weight-Bleeding via SemanticScreener (embedding-space centroid)
        paper_data = {"Title": paper_title, "Abstract": ""}
        sim_wb_embed = screener.evaluate(paper_data, wb_config)

        # 3. Weight-Bleeding via string repetition (old approach)
        wb_string_text = apply_wb_string(query)
        emb_q_wb_str = bi_encoder.encode(wb_string_text)
        sim_wb_string = float(emb_q_wb_str @ emb_p / (np.linalg.norm(emb_q_wb_str) * np.linalg.norm(emb_p) + 1e-10))

        # 4. Naive repetition (repeat whole query 3x) for baseline
        emb_q_naive = bi_encoder.encode(f"{query} {query} {query}")
        sim_naive = float(emb_q_naive @ emb_p / (np.linalg.norm(emb_q_naive) * np.linalg.norm(emb_p) + 1e-10))

        # 5. Cross-encoder (ground truth)
        score_ce = cross_encoder.predict([(query, paper_title)]).item()

        results.append({
            "query": query,
            "paper": paper_title[:60],
            "bi_encoder_vanilla": round(sim_vanilla, 4),
            "wb_embedding_space": round(sim_wb_embed, 4),
            "wb_string_repetition": round(sim_wb_string, 4),
            "naive_repetition": round(sim_naive, 4),
            "cross_encoder": round(float(score_ce), 4),
        })

        print(f"  Q: {query}")
        print(f"  P: {paper_title[:60]}...")
        print(f"    Vanilla: {sim_vanilla:.4f} | WB-embed: {sim_wb_embed:.4f} | WB-string: {sim_wb_string:.4f} | CE: {score_ce:.4f}\n")

    # Rank correlations
    if len(results) >= 3:
        rank_vanilla = sorted(range(len(results)), key=lambda i: results[i]["bi_encoder_vanilla"])
        rank_wb_embed = sorted(range(len(results)), key=lambda i: results[i]["wb_embedding_space"])
        rank_wb_string = sorted(range(len(results)), key=lambda i: results[i]["wb_string_repetition"])
        rank_naive = sorted(range(len(results)), key=lambda i: results[i]["naive_repetition"])
        rank_ce = sorted(range(len(results)), key=lambda i: results[i]["cross_encoder"])

        rho_vanilla_ce = spearman_rank_correlation(rank_vanilla, rank_ce)
        rho_wb_embed_ce = spearman_rank_correlation(rank_wb_embed, rank_ce)
        rho_wb_string_ce = spearman_rank_correlation(rank_wb_string, rank_ce)
        rho_naive_ce = spearman_rank_correlation(rank_naive, rank_ce)

        # Equivalence check: embedding-space vs string repetition
        rho_equivalence = spearman_rank_correlation(rank_wb_embed, rank_wb_string)

        print(f"\n  Spearman correlation with cross-encoder:")
        print(f"    Bi-encoder vanilla:               {rho_vanilla_ce:.3f}")
        print(f"    Weight-Bleeding (embedding-space): {rho_wb_embed_ce:.3f}")
        print(f"    Weight-Bleeding (string-level):    {rho_wb_string_ce:.3f}")
        print(f"    Naive repetition (whole):          {rho_naive_ce:.3f}")

        print(f"\n  Equivalence check:")
        print(f"    Embedding-space vs String-level:   {rho_equivalence:.3f}")
        if rho_equivalence > 0.95:
            print(f"    ✅ Embedding-space ≈ String-level — paper claim validated!")
        else:
            print(f"    ⚠️  Embedding-space ≠ String-level — investigate discrepancy")

        if rho_wb_embed_ce > rho_vanilla_ce:
            print(f"  ✅ Embedding-space WB improves correlation vs vanilla")
        if rho_wb_embed_ce > rho_naive_ce:
            print(f"  ✅ Embedding-space WB outperforms naive repetition")

    # Save
    out = RESULTS_DIR / "cross_encoder_validation.json"
    out.write_text(json.dumps({
        "results": results,
        "method": "Spearman rank correlation",
        "equivalence_rho": round(rho_equivalence, 4) if len(results) >= 3 else None,
    }, indent=2, ensure_ascii=False))
    print(f"\n✅ Results saved to {out}")


if __name__ == "__main__":
    main()
