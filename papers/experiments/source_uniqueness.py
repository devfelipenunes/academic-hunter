#!/usr/bin/env python3
"""Source uniqueness analysis.

Measures how much each academic database contributes *exclusively* to a
multi-source SLR run, and how much overlap exists between sources.

This is the empirical support for the central claim that multi-source
aggregation is not redundant. Third-party comparisons of single-source AI
discovery tools (SciSpace, Consensus, Ai2 Paper Finder — all built on
Semantic Scholar) report ~40% uniqueness between them, because they consult the
same underlying corpus. If a multi-source pipeline shows the same redundancy,
aggregation buys nothing; if overlap is low, each added source is real coverage.

Generates:
  results/source_uniqueness.json

Usage:
    python papers/experiments/source_uniqueness.py [--csv PATH]
"""

import argparse
import collections
import csv
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
RESULTS_DIR = Path(__file__).parent / "results"
DEFAULT_CSV_GLOB = "results/run_*/academic_dataset_*.csv"


def parse_sources(raw: str) -> list[str]:
    """Split a Source cell into individual database names.

    The pipeline joins contributors with ', ' (e.g. 'Crossref, OpenAlex').
    """
    if not raw:
        return []
    return [s.strip() for s in raw.split(",") if s.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=None, help="Run CSV to analyse")
    args = parser.parse_args()

    if args.csv is None:
        candidates = sorted(
            ROOT.glob(DEFAULT_CSV_GLOB), key=lambda p: p.stat().st_size, reverse=True
        )
        if not candidates:
            raise SystemExit(f"No run CSV found matching {DEFAULT_CSV_GLOB}")
        csv_path = candidates[0]
    else:
        csv_path = args.csv

    rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
    total = len(rows)
    if not total:
        raise SystemExit(f"{csv_path} has no rows")

    per_source = collections.Counter()
    source_counts = collections.Counter()  # how many sources found a given paper
    pairwise = collections.Counter()       # frozenset of sources -> papers

    for row in rows:
        sources = parse_sources(row.get("Source", ""))
        source_counts[len(sources)] += 1
        for src in sources:
            per_source[src] += 1
        if sources:
            pairwise[frozenset(sources)] += 1

    exclusive = {src: pairwise.get(frozenset([src]), 0) for src in per_source}
    multi_source = sum(n for k, n in source_counts.items() if k > 1)

    ranked = sorted(per_source.items(), key=lambda kv: -kv[1])
    print("=" * 70)
    print("  Source Uniqueness Analysis")
    print(f"  Corpus: {csv_path.relative_to(ROOT)}")
    print("=" * 70)
    print(f"\n  Papers: {total}")
    print(f"  Found by exactly one source : {source_counts.get(1, 0)} "
          f"({source_counts.get(1, 0) / total:.1%})")
    print(f"  Found by more than one      : {multi_source} ({multi_source / total:.1%})")

    print(f"\n{'Source':<20}{'Found':>8}{'Exclusive':>11}{'% of total':>12}")
    print(f"{'-'*20}{'-'*8}{'-'*11}{'-'*12}")
    for src, found in ranked:
        exc = exclusive.get(src, 0)
        print(f"{src:<20}{found:>8}{exc:>11}{exc / total:>11.1%}")

    # Marginal value: what is lost by dropping a source entirely.
    print(f"\n  Marginal contribution (papers lost if the source is removed):")
    print(f"{'Source':<20}{'Lost':>8}{'% of corpus':>13}")
    print(f"{'-'*20}{'-'*8}{'-'*13}")
    for src, _ in ranked:
        lost = exclusive.get(src, 0)
        print(f"{src:<20}{lost:>8}{lost / total:>12.1%}")

    payload = {
        "description": "Per-source exclusive contribution and overlap in a multi-source run",
        "source_csv": str(csv_path.relative_to(ROOT)),
        "total_papers": total,
        "papers_from_single_source": source_counts.get(1, 0),
        "papers_from_multiple_sources": multi_source,
        "single_source_share": round(source_counts.get(1, 0) / total, 4),
        "per_source_found": dict(ranked),
        "per_source_exclusive": exclusive,
        "multi_source_combination_counts": {
            "+".join(sorted(k)): v for k, v in pairwise.items() if len(k) > 1
        },
        "reference_point": (
            "Third-party comparison reports ~40% uniqueness between single-source "
            "AI discovery tools (SciSpace, Consensus, Ai2 Paper Finder), all built on "
            "Semantic Scholar. Lower overlap here indicates genuine coverage gain."
        ),
    }

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / "source_uniqueness.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"\n✅ Saved to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
