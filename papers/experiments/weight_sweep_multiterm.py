#!/usr/bin/env python3
"""Multi-term weight sweep.

Varies the Weight-Bleeding weights of three domain terms ("sentence
transformer", "bi encoder", "echo embedding") across 64 combinations
(W in {1, 3, 5, 10} each) and measures how the resulting paper ranking
changes. The baseline is W=5 for all three terms.

This script generates ``results/weight_sweep_multiterm.json``, which backs
section 3.7 of the conference paper. It was previously missing from the
repository, leaving those numbers unreproducible.

Scores use the same output transform as the production pipeline
(``sqrt(cosine) * 10``), so the pass-rate thresholds are on the same 0-10
scale as ``settings.min_relevance_score``.

Usage:
    python papers/experiments/weight_sweep_multiterm.py [--n-papers 500]
    python papers/experiments/weight_sweep_multiterm.py --quick   # 2x2x2 sweep
"""

import argparse
import csv
import json
import math
import sys
from itertools import product
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

RESULTS_DIR = Path(__file__).parent / "results"
DEFAULT_CSV_GLOB = "results/run_*/academic_dataset_*.csv"

TERMS = ["sentence transformer", "bi encoder", "echo embedding"]
BASELINE_WEIGHT = 5


def load_papers(n_papers: int, csv_path: Path | None = None) -> list[dict]:
    """Load up to ``n_papers`` records (title + abstract) from a run CSV.

    Picks the largest available run CSV unless one is given explicitly. Rows
    without an abstract are skipped: they carry no semantic signal and would
    score 0 under every weight combination.
    """
    if csv_path is None:
        candidates = sorted(
            ROOT.glob(DEFAULT_CSV_GLOB),
            key=lambda p: p.stat().st_size,
            reverse=True,
        )
        if not candidates:
            raise SystemExit(f"No run CSV found matching {DEFAULT_CSV_GLOB}")
        csv_path = candidates[0]

    papers: list[dict] = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            title = (row.get("Title") or "").strip()
            abstract = (row.get("Abstract") or "").strip()
            if not title or not abstract:
                continue
            papers.append({"title": title, "abstract": abstract})
            if len(papers) >= n_papers:
                break

    print(f"  Loaded {len(papers)} papers from {csv_path.relative_to(ROOT)}")
    return papers


def spearman(a: list[int], b: list[int]) -> float:
    """Spearman rank correlation between two orderings (no scipy dependency)."""
    ra = _ranks(a)
    rb = _ranks(b)
    ra = ra - ra.mean()
    rb = rb - rb.mean()
    denom = math.sqrt((ra**2).sum() * (rb**2).sum())
    return float((ra * rb).sum() / denom) if denom else 0.0


def _ranks(values: list[int]) -> np.ndarray:
    """Average ranks, so ties do not inflate the correlation."""
    arr = np.asarray(values, dtype=float)
    order = arr.argsort()
    ranks = np.empty(len(arr), dtype=float)
    ranks[order] = np.arange(len(arr), dtype=float)
    return ranks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-papers", type=int, default=500, help="Papers to sweep over")
    parser.add_argument("--csv", type=Path, default=None, help="Explicit run CSV to read")
    parser.add_argument("--quick", action="store_true", help="2x2x2 sweep with small sample")
    args = parser.parse_args()

    weights = [1, 10] if args.quick else [1, 3, 5, 10]
    n_papers = 40 if args.quick else args.n_papers

    print("=" * 64)
    print("  Multi-Term Weight Sweep")
    print(f"  Terms: {', '.join(TERMS)}")
    print(f"  Weights: {weights}  ->  {len(weights) ** 3} combinations")
    print("=" * 64)

    from academic_hunter.plugins.screeners import SemanticScreener

    screener = SemanticScreener()
    papers = load_papers(n_papers, args.csv)

    # Embed each paper once: the centroid changes per combination, the papers
    # do not. Evaluating through screener.evaluate() would re-embed every paper
    # for every combination (64 x N forward passes).
    embed = screener.embedding_function
    print("  Embedding papers (once)...")
    paper_vecs = np.asarray(
        [np.asarray(embed([f"{p['title']} {p['abstract']}"])[0], dtype=np.float32) for p in papers]
    )

    def score_combination(combo: tuple[int, ...]) -> np.ndarray:
        """Cosine similarity to the weighted centroid, on the pipeline's 0-10 scale."""
        config = {"technical_weights": dict(zip(TERMS, combo))}
        base_parts, tech_weights = screener._parse_config(config)
        v_ref = screener._get_ref_centroid(base_parts, tech_weights)
        sims = np.asarray([screener._cosine(vec, v_ref) for vec in paper_vecs])
        return np.sqrt(np.clip(sims, 0.0, None)) * 10.0

    combinations = list(product(weights, repeat=3))
    baseline_combo = (BASELINE_WEIGHT,) * 3
    if baseline_combo not in combinations:
        baseline_combo = combinations[0]

    print(f"  Sweeping {len(combinations)} combinations...")
    scores_by_combo = {combo: score_combination(combo) for combo in combinations}

    baseline_order = list(np.argsort(scores_by_combo[baseline_combo]))
    results = []
    unique_rankings = set()
    for combo in combinations:
        scores = scores_by_combo[combo]
        order = list(np.argsort(scores))
        unique_rankings.add(tuple(order))
        results.append({
            "w_st": combo[0],
            "w_be": combo[1],
            "w_echo": combo[2],
            "mean": round(float(scores.mean()), 3),
            "std": round(float(scores.std()), 3),
            "pass_35": int((scores >= 3.5).sum()),
            "pass_50": int((scores >= 5.0).sum()),
            "spearman_vs_baseline": round(spearman(order, baseline_order), 4),
        })

    payload = {
        "description": (
            "Multi-term weight sweep: varying sentence_transformer, bi_encoder, "
            f"echo_embedding weights ({', '.join(map(str, weights))})"
        ),
        "n_papers": len(papers),
        "baseline": f"W={BASELINE_WEIGHT} for all terms",
        "total_combinations": len(combinations),
        "unique_rankings": len(unique_rankings),
        "results": results,
    }

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / "weight_sweep_multiterm.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    rho = [r["spearman_vs_baseline"] for r in results]
    p35 = [r["pass_35"] for r in results]
    p50 = [r["pass_50"] for r in results]
    print(f"\n  Unique rankings      : {len(unique_rankings)} of {len(combinations)}")
    print(f"  Spearman vs baseline : {min(rho):.4f} - {max(rho):.4f}")
    print(f"  Pass rate @3.5       : {min(p35)} - {max(p35)} (of {len(papers)})")
    print(f"  Pass rate @5.0       : {min(p50)} - {max(p50)} (of {len(papers)})")
    print(f"\n✅ Results saved to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
