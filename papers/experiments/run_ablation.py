#!/usr/bin/env python3
"""Ablation study: compare keyword-only, embedding-only, and hybrid scoring.

Usage:
    python papers/experiments/run_ablation.py [--quick]

Runs the same search configuration across 3 scoring modes.

**Read `excluded_score`, not `Final`.** The ablation mode acts at *ingest*: it
decides which papers pass the inclusion threshold (`_hybrid_score` against
`min_inclusion_score`). The reported `Relevance_Score` is written later by
`RecomputeRanksStep`, which fuses the keyword and embedding scores — and both of
those are computed the same way regardless of mode. The reported outcome is
therefore **mode-independent by construction**, and so is `Final`, and so are
`Top-1`/`Top-5`.

That was not always true: ingest used to write `Relevance_Score` directly, so
the mode did propagate. Once the two scores were separated (one writer each), the
mode's effect became confined to `excluded_score` — the count of papers the
ingest gate rejected.

Measured on the 2026-09-10 regeneration, the modes with identical source data
(keyword and embedding, both 1249 identified) produced `excluded_score` 0 and 79
respectively, yet an identical `Final` of 150 and an identical exported set
(Jaccard 1.000 in `overlap_analysis.py`). The residual spread in `Identified`
between runs is the HTTP cache and live sources, not the scoring mode.

A table reporting `Final` across modes is therefore measuring run-to-run source
variation. This summary prints the mode-dependent quantity for that reason.
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

    # Record which configuration produced these numbers. The script reads the
    # live config.json, so a run against a different topic yields entirely
    # different counts — without this, results are not attributable to a corpus.
    # The SHA-256 covers the whole file (anchors, technical_strings, weights,
    # settings), which is more reliable than enumerating known fields.
    import hashlib

    _cfg = HunterConfig()
    _cfg_path = Path("config.json")
    config_fingerprint = {
        "config_sha256": (
            hashlib.sha256(_cfg_path.read_bytes()).hexdigest() if _cfg_path.exists() else None
        ),
        "anchors": sorted(_cfg.anchors.keys()),
        "limit_per_query": _cfg.settings.get("limit_per_query"),
        "start_year": _cfg.settings.get("start_year"),
        "min_relevance_score": _cfg.settings.get("min_relevance_score"),
    }

    results = []
    for mode, label in MODES:
        result = run_mode(mode, label)
        results.append(result)

        if quick:
            break  # only first mode for quick test

    # Summary table
    print(f"\n\n{'='*60}")
    print(f"  ABLATION RESULTS SUMMARY")
    print(f"{'='*78}")
    print(
        f"{'Mode':<12} {'Identified':>10} {'Excl(anchors)':>14} "
        f"{'Excl(score)':>12} {'Final':>7} {'Top-1':>7}"
    )
    print(f"{'-'*12} {'-'*10} {'-'*14} {'-'*12} {'-'*7} {'-'*7}")
    for r in results:
        print(
            f"{r['mode']:<12} {r['identified']:>10} {r['excluded_anchors']:>14} "
            f"{r['excluded_score']:>12} {r['final_included']:>7} "
            f"{r['top_5_scores'][0]:>7}"
        )

    # The mode acts only on `excluded_score`; `Final` and the top scores are
    # produced by a fusion that does not depend on the mode. Say so, so the
    # table is not read as an ablation of the reported score.
    excluded = [r["excluded_score"] for r in results]
    finals = {r["final_included"] for r in results}
    print()
    if len(set(excluded)) == 1:
        print("  Note: every mode rejected the same number of papers at ingest, so")
        print("        this corpus shows no mode effect. Compare `Excl(score)`.")
    else:
        print(f"  Mode-dependent quantity is `Excl(score)`: {excluded}.")
    if len(finals) == 1:
        print(
            f"  All modes report the same Final ({finals.pop()}) — expected, since the "
            "reported\n  score is fused from signals that do not depend on the mode."
        )

    # Save results. A --quick run covers only the first mode, so it must not
    # clobber the canonical 3-mode file — that is how the committed
    # ablation_results.json ended up containing keyword-mode data only, while
    # the paper reported all three modes.
    out = RESULTS_DIR / ("ablation_results_quick.json" if quick else "ablation_results.json")
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\n✅ Results saved to {out}")

    # Sidecar metadata: results stay a bare list (overlap_analysis.py and
    # validate_innovation_claims.py iterate over it directly), but the run must
    # be attributable to a corpus — the same script on a different config.json
    # produces entirely different counts.
    meta = RESULTS_DIR / "ablation_run_metadata.json"
    meta.write_text(json.dumps(config_fingerprint, indent=2, ensure_ascii=False))
    print(f"✅ Config fingerprint saved to {meta}")
    print(f"   anchors: {config_fingerprint['anchors']}")

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
