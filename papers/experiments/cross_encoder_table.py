#!/usr/bin/env python3
"""Reproduce Table 4 — cross-encoder correlation by query group.

Reads ``results/cross_encoder_expanded.json`` (20 query-paper pairs) and
recomputes the Spearman rank correlation of the vanilla bi-encoder and
Weight-Bleeding against the ms-marco cross-encoder, per query group.

Group boundaries follow the file order: the first 10 pairs are in-domain SLR,
the next 5 related AI/ML, the last 5 intentionally unrelated negatives. This
script exists because the numbers in Table 4 were previously not reproducible
from any committed script, and had drifted from the raw data.

Usage:
    python papers/experiments/cross_encoder_table.py
"""

import json
import sys
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
SOURCE = RESULTS_DIR / "cross_encoder_expanded.json"

# (label, start, end) — half-open slices over the results list
GROUPS = [
    ("SLR (in-domain)", 0, 10),
    ("AI/ML (related)", 10, 15),
    ("Negative (unrelated)", 15, 20),
]


def spearman(x: list[float], y: list[float]) -> float:
    """Spearman rho via scipy (average ranks on ties — the literature default)."""
    try:
        from scipy.stats import spearmanr
    except ImportError:
        raise SystemExit(
            "scipy is required for reproducible tie handling: pip install scipy"
        )
    return float(spearmanr(x, y).statistic)


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"Missing {SOURCE}. Run cross_encoder_val.py first.")

    payload = json.loads(SOURCE.read_text())
    results = payload["results"] if isinstance(payload, dict) else payload

    print("=" * 68)
    print("  Table 4 — Spearman rho vs cross-encoder, by query group")
    print(f"  Source: {SOURCE.relative_to(Path(__file__).parent.parent.parent)}")
    print("=" * 68)

    rows = []
    for label, start, end in GROUPS:
        chunk = results[start:end]
        if not chunk:
            continue
        ce = [r["cross_encoder"] for r in chunk]
        vanilla = [r["bi_encoder_vanilla"] for r in chunk]
        wb = [r["weight_bleeding"] for r in chunk]
        rows.append((label, len(chunk), spearman(vanilla, ce), spearman(wb, ce)))

    print(f"\n{'Group':<22}{'Pairs':>6}{'Vanilla':>12}{'WB':>10}")
    print(f"{'-'*22}{'-'*6}{'-'*12}{'-'*10}")
    for label, n, rho_v, rho_w in rows:
        print(f"{label:<22}{n:>6}{rho_v:>12.3f}{rho_w:>10.3f}")

    print("\n  LaTeX:")
    print(r"  \begin{tabular}{lrrr}")
    print(r"  \toprule")
    print(r"  Group & Pairs & Vanilla $\rho$ & WB $\rho$ \\")
    print(r"  \midrule")
    for label, n, rho_v, rho_w in rows:
        print(f"  {label} & {n} & {rho_v:.3f} & {rho_w:.3f} \\\\")
    print(r"  \bottomrule")
    print(r"  \end{tabular}")
    print(f"\n  Table 4 in papers/conference-2027/paper.md must match these values.")


if __name__ == "__main__":
    main()
