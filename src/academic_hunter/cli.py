import argparse
import json
import logging
import time
from pathlib import Path
from academic_hunter import AcademicHunter
from academic_hunter.core.infra.config import HunterConfig

MODES = [
    ("keyword", "Keyword-only (regex, no embedding)"),
    ("embedding", "Embedding-only (Weight-Bleeding, no regex)"),
    ("hybrid", "Hybrid (70% keyword + 30% embedding)"),
]


def run_scraper():
    """Entry point for the main script."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    parser = argparse.ArgumentParser(description="Academic Hunter")
    parser.add_argument("--limit", type=int, default=None, help="Limit per source (overrides config)")
    parser.add_argument("--benchmark", action="store_true", help="Run ablation benchmark (3 modes)")
    args = parser.parse_args()

    if args.benchmark:
        return run_benchmark(args.limit)

    hunter = AcademicHunter()
    if args.limit is not None:
        hunter.run(limit_per_source=args.limit)
    else:
        limit = hunter.config.settings.get("limit_per_query", 100)
        hunter.run(limit_per_source=limit)


def run_benchmark(limit_per_source=None):
    """Run all 3 scoring modes and generate comparison report."""
    print("=" * 60)
    print("  Academic Hunter — Benchmark Mode")
    print("  Comparing keyword vs embedding vs hybrid scoring")
    print("=" * 60)

    results = []
    for mode, label in MODES:
        print(f"\n  MODE: {label}")
        config = HunterConfig()
        config.settings.setdefault("ablation", {})["mode"] = mode
        config.save()

        hunter = AcademicHunter()
        t0 = time.time()
        limit = limit_per_source or config.settings.get("limit_per_query", 100)
        report_path = hunter.run(limit_per_source=limit)
        elapsed = time.time() - t0

        n_identified = sum(hunter.stats["identified"].values())
        n_final = hunter.stats["included_final"]
        scores = sorted(
            (p.get("Relevance_Score", 0) for p in hunter.consolidated_results.values()),
            reverse=True,
        )[:5]

        results.append({
            "mode": mode,
            "identified": n_identified,
            "excluded_year": hunter.stats.get("excluded_year", 0),
            "excluded_anchors": hunter.stats.get("excluded_anchors", 0),
            "excluded_score": hunter.stats.get("excluded_technical_score", 0),
            "final_included": n_final,
            "top_5_scores": scores,
            "elapsed_s": round(elapsed, 1),
        })
        print(f"  ✓ {n_final} papers included in {elapsed:.0f}s")

    # Summary
    print(f"\n{'='*60}")
    print(f"  BENCHMARK RESULTS")
    print(f"{'='*60}")
    print(f"{'Mode':<20} {'Identified':>10} {'Final':>8} {'Excl Score':>10} {'Top-1':>8} {'Time':>8}")
    print(f"{'-'*20} {'-'*10} {'-'*8} {'-'*10} {'-'*8} {'-'*8}")
    for r in results:
        print(f"{r['mode']:<20} {r['identified']:>10} {r['final_included']:>8} {r['excluded_score']:>10} {r['top_5_scores'][0]:>8} {r['elapsed_s']:>7.0f}s")

    # Save
    out_path = Path("results") / "benchmark_results.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\n✅ Benchmark saved to {out_path}")

    # Restore hybrid
    config = HunterConfig()
    config.settings.setdefault("ablation", {})["mode"] = "hybrid"
    config.save()
    print(f"✅ Config restored to hybrid mode")

if __name__ == "__main__":
    run_scraper()
