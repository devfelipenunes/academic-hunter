"""Measure the fusion rules on a run's own signals. Command-line front end.

The logic lives in :mod:`academic_hunter.core.evaluation.comparison` — the MCP
tool has to import it, and a root-level script directory is not on the installed
package's path. This file exists under the name ``evaluation/README.md`` already
cites, so the caveat that the comparator "is not in this repository" is replaced
by a command that runs.

Usage::

    python evaluation/fusion_comparison.py \\
        results/run_*/score_distribution_*.json \\
        evaluation/qrels_blockchain_ai.json

The qrels must judge the same topic as the run whose distribution is given: the
pool ids are the join between them, and a collection judged against another
run's pool produces a table of empty cells. The script says so rather than
printing zeros.

A pool is not a qrels. ``pool_candidates_*.json`` is the list of documents to
grade, and handing it here gets "queries must be a non-empty object" — the
judged collection is what the grading page exports once someone has graded it.
"""

import argparse
import sys

from academic_hunter.core.evaluation import QrelsError, load_qrels
from academic_hunter.core.evaluation.comparison import (
    DEFAULT_KS,
    DEFAULT_TOP_K,
    compare,
    load_distribution,
    render,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("distribution", help="a run's score_distribution_*.json")
    parser.add_argument("qrels", help="the judged collection to measure against")
    parser.add_argument(
        "--top-k", type=int, default=DEFAULT_TOP_K, help="documents kept per query"
    )
    parser.add_argument(
        "--ks",
        default=",".join(str(k) for k in DEFAULT_KS),
        help="comma-separated rank cutoffs whose nDCG is reported",
    )
    args = parser.parse_args()

    cutoffs = tuple(int(k) for k in args.ks.split(",") if k.strip())
    try:
        result = compare(
            load_distribution(args.distribution),
            load_qrels(args.qrels),
            top_k=args.top_k,
            ks=cutoffs,
            judged_collection=args.qrels,
        )
    except (QrelsError, ValueError, OSError) as e:
        print(f"cannot compare: {e}", file=sys.stderr)
        raise SystemExit(2) from e
    print(render(result))


if __name__ == "__main__":
    main()
