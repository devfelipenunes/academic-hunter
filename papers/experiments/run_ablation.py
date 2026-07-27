#!/usr/bin/env python3
"""Ablation study: compare keyword-only, embedding-only, and hybrid scoring.

Usage:
    python papers/experiments/run_ablation.py [--quick]

Runs the same search configuration across 3 scoring modes and reports
how many papers pass the relevance threshold in each mode.
"""

import json
import sys
import time
from pathlib import Path

SRC = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(SRC))

from academic_hunter import AcademicHunter
from academic_hunter.core.infra.config import HunterConfig

MODES = [
    ("keyword",  "Keyword-only (regex, no embedding)"),
    ("embedding","Embedding-only (Weight-Bleeding, no regex)"),
    ("hybrid",   "Hybrid (70% keyword + 30% embedding)"),
]

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def run_mode(mode: str, label: str) -> dict:
    """Run AcademicHunter in the given ablation mode and collect stats."""
    print(f"\n{'='*60}")
    print(f"  MODE: {label}")
    print(f"{'='*60}")

    # Update config for this mode
    config = HunterConfig()
    config.settings.setdefault("ablation", {})["mode"] = mode
    config.save()

    # Run search
    hunter = AcademicHunter()
    t0 = time.time()
    report_path = hunter.run(limit_per_source=50)
    elapsed = time.time() - t0

    n_identified = sum(hunter.stats["identified"].values())
    n_final = hunter.stats["included_final"]

    # Top-5 scores
    scores = sorted(
        (p.get("Relevance_Score", 0) for p in hunter.consolidated_results.values()),
        reverse=True,
    )[:5]

    result = {
        "mode": mode,
        "label": label,
        "elapsed_s": round(elapsed, 1),
        "identified": n_identified,
        "duplicates_removed": hunter.stats["duplicates_removed"],
        "excluded_year": hunter.stats.get("excluded_year", 0),
        "excluded_anchors": hunter.stats.get("excluded_anchors", 0),
        "excluded_score": hunter.stats.get("excluded_technical_score", 0),
        "final_included": n_final,
        "top_5_scores": scores,
        "report": report_path,
    }

    print(f"\n  ✓ {n_final} papers included of {n_identified} identified")
    print(f"  ✓ Top-5 scores: {scores}")
    print(f"  ✓ Elapsed: {elapsed:.1f}s")
    print(f"  ✓ Report: {report_path}")

    return result


def main():
    quick = "--quick" in sys.argv

    print("=" * 60)
    print("  Academic Hunter — Ablation Study")
    print("  Comparing keyword vs embedding vs hybrid scoring")
    print("=" * 60)

    results = []
    for mode, label in MODES:
        result = run_mode(mode, label)
        results.append(result)

        if quick:
            break  # only first mode for quick test

    # Summary table
    print(f"\n\n{'='*60}")
    print(f"  ABLATION RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"{'Mode':<25} {'Identified':>10} {'Final':>8} {'Top-1':>8} {'Top-5':>20}")
    print(f"{'-'*25} {'-'*10} {'-'*8} {'-'*8} {'-'*20}")
    for r in results:
        top5 = ", ".join(str(s) for s in r["top_5_scores"])
        print(f"{r['mode']:<25} {r['identified']:>10} {r['final_included']:>8} {r['top_5_scores'][0]:>8} {top5:>20}")

    # Save results
    out = RESULTS_DIR / "ablation_results.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\n✅ Results saved to {out}")

    # LaTeX table
    if len(results) == 3:
        latex = r"""\begin{table}[h]
\centering
\caption{Ablation study results comparing scoring modes.}
\label{tab:ablation}
\begin{tabular}{lrrrr}
\toprule
Mode & Identified & Final Included & Top-1 Score & Top-5 Avg \\"""
        for r in results:
            top5_avg = sum(r["top_5_scores"]) / len(r["top_5_scores"])
            latex += f"\n{r['mode']} & {r['identified']} & {r['final_included']} & {r['top_5_scores'][0]} & {top5_avg:.1f} \\\\"
        latex += r"""
\bottomrule
\end{tabular}
\end{table}"""

        tex_path = RESULTS_DIR / "tables" / "ablation_table.tex"
        tex_path.parent.mkdir(exist_ok=True)
        tex_path.write_text(latex)
        print(f"\n✅ LaTeX table saved to {tex_path}")


if __name__ == "__main__":
    main()
