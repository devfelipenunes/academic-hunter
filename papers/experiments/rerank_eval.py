#!/usr/bin/env python3
"""Measure the cross-encoder reranker against the judged collection.

Companion to ``retrieval_eval.py``, which compares *first-stage* rankers. This
one holds the first stage fixed (BM25, the shipped query-mode signal) and varies
the second: how many of the ranking's head documents the cross-encoder gets to
reorder.

It calls the shipped code rather than a paraphrase of it
-------------------------------------------------------
The first stage is ``fuse_scores`` — the function the pipeline calls — and the
reordering is ``rerank_scores``, the rule ``_apply_rerank`` applies. An
experiment that reimplements either is free to drift from the product, and then
the number stops describing what ships. This is the same argument
``core/nlp/fusion.py`` makes for keeping the fusion a pure function.

The pool is not chosen by the metric under test
-----------------------------------------------
Each query is ranked over the **judged pool only** — the documents carrying a
grade, as ``documents_for`` returns them. The cross-encoder reorders *within*
that pool; it never selects it. Taking "the top-N by BM25" is candidate
selection for reranking, which is what the pipeline does, and is not the same as
choosing which documents get judged. The qrels pool was built as
``top-30-by-score UNION random-30(seed=20260910)`` for that reason, and
``tests/test_evaluation_collection.py`` pins the property.

The oracle is the ceiling
-------------------------
``ce_oracle`` reranks the whole pool, so it is what the cross-encoder could
achieve with unlimited budget. If the oracle does not beat BM25, no ``top_n``
will. ``top_n=20`` reaching ~97% of it is what makes a small head sufficient.

Usage:
    python papers/experiments/rerank_eval.py
    python papers/experiments/rerank_eval.py --top-n 5,10,20
    python papers/experiments/rerank_eval.py --qrels path/to/qrels.json
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from retrieval_eval import load_documents

from academic_hunter.core.evaluation import (
    Timing,
    documents_for,
    evaluate_run,
    load_qrels,
    mean_metrics,
    topics,
)
from academic_hunter.core.nlp import BM25, fuse_scores
from academic_hunter.core.nlp.model_cache import (
    DEFAULT_CE_MAX_LENGTH,
    DEFAULT_CE_MODEL,
    get_cross_encoder,
)
from academic_hunter.core.nlp.reranker import rerank_scores

RESULTS_DIR = Path(__file__).parent / "results"
DEFAULT_QRELS = ROOT / "papers" / "evaluation" / "qrels_pilot_genre_analysis.json"
KS = (5, 10, 20)
DEFAULT_TOP_N = (5, 10, 20, 30)
#: Key of the first-stage row, shared by the tables, the topic deltas and the JSON.
BASELINE = "bm25 (first stage)"
ORACLE = "ce_oracle (ceiling)"


def rank_by(ids, scores):
    """Ids best-first, ties broken by id: the total order the pipeline uses."""
    return [i for _, i in sorted(zip(scores, ids), key=lambda pair: (-pair[0], pair[1]))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qrels", default=str(DEFAULT_QRELS), help="judged collection")
    parser.add_argument(
        "--top-n",
        default=",".join(str(n) for n in DEFAULT_TOP_N),
        help="comma-separated head sizes to sweep (default: 5,10,20,30)",
    )
    parser.add_argument(
        "--no-oracle",
        action="store_true",
        help="skip the whole-pool rerank (the oracle ceiling)",
    )
    args = parser.parse_args()

    try:
        top_ns = [int(n) for n in args.top_n.split(",") if n.strip()]
    except ValueError:
        print(f"--top-n must be a comma-separated list of integers: {args.top_n!r}")
        return 2

    qrels_path = Path(args.qrels)
    qrels = load_qrels(qrels_path)
    documents, _ = load_documents(qrels_path)

    # Title + Abstract is a property of the document, not of the query, so it is
    # built once instead of per query.
    doc_text = {
        doc_id: f"{doc.get('Title', '')} {doc.get('Abstract', '')}"
        for doc_id, doc in documents.items()
    }

    print("=" * 78)
    print("  Cross-encoder rerank evaluation")
    print("=" * 78)
    print(f"  qrels     : {qrels_path.relative_to(ROOT)}")
    print(f"  documents : {len(documents)} judged")
    print(f"  model     : {DEFAULT_CE_MODEL} (max_length={DEFAULT_CE_MAX_LENGTH})")
    print()

    load_started = time.perf_counter()
    model = get_cross_encoder()
    load_seconds = time.perf_counter() - load_started
    if model is None:
        print("sentence-transformers is not available. Install the 'ml' extra:")
        print("   pip install 'academic-hunter[ml]'")
        return 1
    print(f"  model loaded in {load_seconds:.1f} s\n")

    rows = {n: {} for n in top_ns}
    baseline, oracle = {}, {}
    timing = Timing()

    for query_id, judgment in qrels.queries.items():
        pool = list(documents_for(qrels, query_id))
        corpus = [doc_text[doc_id] for doc_id in pool]

        first_stage = fuse_scores(
            BM25(corpus).score(judgment.text),
            [0.0] * len(pool),
            weights={"keyword": 1.0, "embedding": 0.0},
        )
        order = rank_by(pool, first_stage)
        baseline[query_id] = order

        # The oracle needs the whole pool; otherwise the widest sweep bounds what
        # has to be scored, since only the top-N of `order` is ever reranked.
        to_score = len(pool) if not args.no_oracle else min(max(top_ns), len(pool))
        head_ids = order[:to_score]

        started = time.perf_counter()
        scores = model.predict([[judgment.text, doc_text[d]] for d in head_ids])
        timing.per_query[query_id] = time.perf_counter() - started
        timing.pool_size[query_id] = len(head_ids)
        by_id = dict(zip(head_ids, (float(s) for s in scores)))

        index_of = {doc_id: i for i, doc_id in enumerate(pool)}
        for n in top_ns:
            head = order[:n]
            ce_order = sorted(head, key=lambda d: (-by_id[d], d))
            # The shipped rule, over the shipped first-stage scores: it
            # redistributes the head's band, so the final order is a sort of the
            # result rather than a splice of the cross-encoder's order.
            reranked = rerank_scores(first_stage, [index_of[d] for d in ce_order])
            rows[n][query_id] = rank_by(pool, reranked)

        if not args.no_oracle:
            oracle[query_id] = rank_by(pool, [by_id[d] for d in pool])

    strategies = {BASELINE: baseline}
    for n in top_ns:
        strategies[f"bm25 + rerank@{n}"] = rows[n]
    if not args.no_oracle:
        strategies[ORACLE] = oracle

    reports = {}
    print("-" * 78)
    print(f"  {'strategy':<24} {'nDCG@5':>8} {'nDCG@10':>8} {'nDCG@20':>8} {'MRR':>8}")
    print("-" * 78)
    for name, rankings in strategies.items():
        report = evaluate_run(qrels, rankings, ks=KS)
        reports[name] = report
        mean = report.mean
        print(
            f"  {name:<24} {mean['ndcg@5']:>8.4f} {mean['ndcg@10']:>8.4f} "
            f"{mean['ndcg@20']:>8.4f} {mean['mrr']:>8.4f}"
        )
    print("-" * 78)

    per_pair = timing.seconds_per_document * 1000
    print()
    print(f"  {'cross-encoder pass':<24}{'total s':>10}{'ms / pair':>12}{'pairs':>9}")
    print("  " + "-" * 53)
    print(f"  {'cross-encoder pass':<24}{timing.total_seconds:>10.2f}"
          f"{per_pair:>12.1f}{timing.total_documents:>9}")
    print()

    # A mean over two unrelated corpora hides which one was helped, and a gain
    # that lifts one topic while wrecking the other is not a gain. Every topic
    # here has an entry in every report, so a missing value is a bug, not a gap.
    print("  nDCG@10 by topic")
    by_topic = {}
    for topic, query_ids in topics(qrels).items():
        row = {}
        for name, report in reports.items():
            subset = [report.per_query[q] for q in query_ids if q in report.per_query]
            row[name] = mean_metrics(subset).get("ndcg@10") if subset else None
        by_topic[topic] = row
        print(f"\n    {topic}")
        for name, value in row.items():
            delta = (
                value - row[BASELINE]
                if value is not None and row[BASELINE] is not None
                else 0.0
            )
            marker = f"  ({delta:+.4f})" if name != BASELINE else ""
            shown = f"{value:.4f}" if value is not None else "n/a"
            print(f"      {name:<24} {shown}{marker}")

    print(f"\n  inference: {timing.total_seconds:.1f} s / {timing.total_documents} pairs "
          f"= {per_pair:.0f} ms per pair")
    print(f"  model load: {load_seconds:.1f} s (once per process, cached in the pipeline)")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "rerank_eval.json"
    payload = {
        "qrels": str(qrels_path.relative_to(ROOT)),
        "document_count": len(documents),
        "ks": list(KS),
        "model": {
            "id": DEFAULT_CE_MODEL,
            "max_length": DEFAULT_CE_MAX_LENGTH,
            "load_seconds": round(load_seconds, 3),
        },
        "remap_rule": (
            "core.nlp.reranker.rerank_scores — called directly, not reimplemented"
        ),
        "strategies": {name: report.as_dict() for name, report in reports.items()},
        "by_topic": by_topic,
        "timing": timing.as_dict(),
        "notes": {
            "timing_unit": (
                "seconds per (query, candidate) pair scored by the cross-encoder; "
                "a smaller top_n scores proportionally fewer pairs"
            ),
            "scored_per_query": (
                "the whole pool when the oracle runs, otherwise max(top_n)"
            ),
        },
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\n  artifact: {out_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
