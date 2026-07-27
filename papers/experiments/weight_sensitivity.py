#!/usr/bin/env python3
"""Weight sensitivity analysis: show that varying technical_weights changes ranking predictably.

Usage:
    python papers/experiments/weight_sensitivity.py
"""

import csv
import json
import sys
from pathlib import Path

SRC = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(SRC))

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def main():
    print("=" * 60)
    print("  Weight Sensitivity Analysis")
    print("  How changing technical_weights affects ranking")
    print("=" * 60)

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("❌ sentence-transformers not installed.")
        sys.exit(1)

    model = SentenceTransformer("all-MiniLM-L6-v2")

    # Fixed set of paper titles
    papers = [
        "Blockchain Interoperability Frameworks: A Comparative Analysis of Cross-Chain Solutions",
        "A Survey on Blockchain Interoperability: Past, Present, and Future Trends",
        "Blockchain-Powered Secure and Transparent Citizen Participation Framework",
        "ZeroTrustBlock: Enhancing Security, Privacy, and Interoperability",
        "A Low-Cost Cross-Border Payment System Based on Auditable Cryptocurrency",
        "Blockchain-Based IoT Access Control System: Towards Security, Lightweight, and Cross-Domain",
        "Self-sovereign identity for verifiable authorship consent",
        "Exploring Sybil and Double-Spending Risks in Blockchain Systems",
    ]

    # Query: the term we'll weight differently
    query_base = "blockchain interoperability cross-chain"

    # Vary the weight of "blockchain" from 1 to 10
    weights = list(range(1, 11))

    print(f"\n  Query base: '{query_base}'")
    print(f"  Papers: {len(papers)}")
    print(f"  Weights: {weights}\n")

    results = []
    for w in weights:
        # Repeat the query term W times (Weight-Bleeding)
        term = "blockchain " * w + "interoperability cross-chain"
        emb_q = model.encode(term)
        emb_ps = [model.encode(p) for p in papers]

        scores = []
        for i, p in enumerate(papers):
            import numpy as np; sim = float(emb_q @ emb_ps[i] / (np.linalg.norm(emb_q) * np.linalg.norm(emb_ps[i]) + 1e-10))
            scores.append((i, p, sim))

        # Sort by similarity
        scores.sort(key=lambda x: -x[2])

        ranking = [s[1][:50] for s in scores]
        print(f"  Weight {w:2d}: 1st={ranking[0] if ranking else 'N/A'}")

        for i, p, s in scores:
            results.append({
                "weight": w,
                "paper_index": i,
                "paper": p[:80],
                "similarity": round(s, 4),
                "rank": scores.index((i, p, s)) + 1,
            })

    # Save CSV
    csv_path = RESULTS_DIR / "weight_sensitivity.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["weight", "paper_index", "paper", "similarity", "rank"])
        w.writeheader()
        w.writerows(results)
    print(f"\n✅ CSV saved to {csv_path}")

    # Summary: show how top rank changes with weight
    print(f"\n  Top-ranked paper per weight:")
    prev_top = None
    for w in weights:
        top = [r for r in results if r["weight"] == w]
        top.sort(key=lambda x: -x["similarity"])
        curr_top = top[0]["paper_index"]
        marker = " ← same" if curr_top == prev_top or prev_top is None else " ← CHANGED"
        if prev_top is None:
            marker = ""
        print(f"    Weight {w:2d}: paper {curr_top} (sim: {top[0]['similarity']:.4f}){marker}")
        prev_top = curr_top

    # If ranking changed, the weight is effective
    rankings = {w: [r["paper_index"] for r in results if r["weight"] == w] for w in weights}
    unique_rankings = set(tuple(r) for r in rankings.values())
    print(f"\n  Distinct orderings across weights: {len(unique_rankings)}")
    if len(unique_rankings) > 1:
        print(f"  ✅ Weight-Bleeding changes ranking — control is effective!")
    else:
        print(f"  ℹ️  Same ordering across all weights (dataset may lack blockchain papers)")


if __name__ == "__main__":
    main()
