#!/usr/bin/env python3
"""Measure the cross-encoder reranker against the judged collection.

Companion to ``retrieval_eval.py``, which compares *first-stage* rankers. This
one holds the first stage fixed (BM25, the shipped query-mode signal) and varies
the second: how many of the head documents the cross-encoder gets to reorder.

Why a separate script rather than a mode of its own in the sibling
-----------------------------------------------------------------
``retrieval_eval``'s contract is ``factory(corpus) -> scorer(doc, query)``,
which fits a reranker poorly: its ``Timing`` would start counting (query,
document) pairs while still reporting them as documents, changing the meaning of
``seconds_per_document`` without changing its name. The sweeps here (several
``top_n`` values, plus an oracle) are not shared either.

The pool is not chosen by the metric under test
-----------------------------------------------
Each query is ranked over the **judged pool only** — the documents carrying a
grade, as ``documents_for`` returns them. The cross-encoder reorders *within*
that pool; it never selects it. Picking "the top-N by BM25" is candidate
selection for reranking, which is exactly what the pipeline does, and is not the
same thing as choosing which documents get judged. The qrels pool was built as
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

from academic_hunter.core.evaluation import documents_for, evaluate_run, load_qrels
from academic_hunter.core.nlp import BM25, fuse_scores

RESULTS_DIR = Path(__file__).parent / "results"
DEFAULT_QRELS = ROOT / "papers" / "evaluation" / "qrels_pilot_genre_analysis.json"
KS = (5, 10, 20)
DEFAULT_TOP_N = (5, 10, 20, 30)
#: Same model the pipeline ships with; see `core/nlp/reranker.py`.
MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
#: Matches `settings.rerank.max_length` and the `rerank_search` tool.
MAX_LENGTH = 512


def build_first_stage(documents, query):
    """BM25 over the corpus, fused exactly as ``RecomputeRanksStep`` fuses it.

    Query mode defaults to BM25 alone (weight 1.0 on the sparse signal, 0.0 on
    the embedding) because adding the embedding measured monotonically worse.
    Calling the shipped ``fuse_scores`` rather than reimplementing the
    normalisation is the point: an experiment that reimplements the rule is free
    to drift from it, and then the measurement stops describing the product.
    """
    corpus = [
        f"{documents[doc_id].get('Title', '')} {documents[doc_id].get('Abstract', '')}"
        for doc_id in documents
    ]
    raw = BM25(corpus).score(query)
    return fuse_scores(
        raw, [0.0] * len(documents), weights={"keyword": 1.0, "embedding": 0.0}
    )


def rank_by(ids, scores):
    """Descending by score, ties broken by document id for determinism."""
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
        print(f"❌ --top-n must be a comma-separated list of integers: {args.top_n!r}")
        return 2

    qrels_path = Path(args.qrels)
    qrels = load_qrels(qrels_path)
    documents, _ = load_documents(qrels_path)

    rows = {n: {} for n in top_ns}
    baseline, oracle = {}, {}
    strategy_names = ["bm25"]

    try:
        from sentence_transformers import CrossEncoder
    except ImportError:
        print("❌ sentence-transformers not installed. Install the 'ml' extra:")
        print("   pip install 'academic-hunter[ml]'")
        return 1

    print("=" * 78)
    print("  Cross-encoder rerank evaluation")
    print("=" * 78)
    print(f"  qrels     : {qrels_path.relative_to(ROOT)}")
    print(f"  documents : {len(documents)} judged")
    print(f"  model     : {MODEL} (max_length={MAX_LENGTH})")
    print()

    load_started = time.perf_counter()
    model = CrossEncoder(MODEL, max_length=MAX_LENGTH)
    load_seconds = time.perf_counter() - load_started
    print(f"  model loaded in {load_seconds:.1f} s\n")

    pairs_scored = 0
    infer_started = time.perf_counter()

    for query_id, judgment in qrels.queries.items():
        pool = list(documents_for(qrels, query_id))
        texts = {
            doc_id: f"{documents[doc_id].get('Title', '')} "
                    f"{documents[doc_id].get('Abstract', '')}"
            for doc_id in pool
        }

        first_stage = build_first_stage({d: documents[d] for d in pool}, judgment.text)
        order = rank_by(pool, first_stage)
        baseline[query_id] = order

        # One pass over the pool. The cross-encoder scores a pair in isolation
        # — a document's score does not depend on its neighbours — so slicing
        # the top-N out of this is identical to scoring only those N, and the
        # whole sweep costs a single pass.
        scores = model.predict([[judgment.text, texts[d]] for d in pool])
        pairs_scored += len(pool)
        by_id = dict(zip(pool, (float(s) for s in scores)))

        for n in top_ns:
            head, tail = order[:n], order[n:]
            reranked = sorted(head, key=lambda d: (-by_id[d], d))
            rows[n][query_id] = reranked + tail

        if not args.no_oracle:
            oracle[query_id] = rank_by(pool, [by_id[d] for d in pool])

    infer_seconds = time.perf_counter() - infer_started
    ms_per_pair = 1000 * infer_seconds / pairs_scored if pairs_scored else 0.0

    strategies = {"bm25 (first stage)": baseline}
    for n in top_ns:
        strategies[f"bm25 + rerank@{n}"] = rows[n]
        strategy_names.append(f"bm25 + rerank@{n}")
    if not args.no_oracle:
        strategies["ce_oracle (ceiling)"] = oracle
        strategy_names.append("ce_oracle (ceiling)")

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

    # A mean over two unrelated corpora hides which one was helped, and a gain
    # that lifts one topic while wrecking the other is not a gain.
    print("\n  nDCG@10 by topic")
    by_topic = {}
    for topic in sorted({j.topic for j in qrels.queries.values()}):
        query_ids = [q for q, j in qrels.queries.items() if j.topic == topic]
        subset = type(qrels)(queries={q: qrels.queries[q] for q in query_ids})
        row = {}
        for name, rankings in strategies.items():
            row[name] = evaluate_run(subset, rankings, ks=KS).mean["ndcg@10"]
        by_topic[topic] = row
        print(f"\n    {topic}")
        for name, value in row.items():
            delta = value - row["bm25 (first stage)"]
            marker = f"  ({delta:+.4f})" if name != "bm25 (first stage)" else ""
            print(f"      {name:<24} {value:.4f}{marker}")

    print(f"\n  inference: {infer_seconds:.1f} s / {pairs_scored} pairs "
          f"= {ms_per_pair:.0f} ms per pair")
    print(f"  model load: {load_seconds:.1f} s (once per process, cached in the pipeline)")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "rerank_eval.json"
    payload = {
        "qrels": str(qrels_path.relative_to(ROOT)),
        "document_count": len(documents),
        "ks": list(KS),
        "model": {
            "id": MODEL,
            "max_length": MAX_LENGTH,
            "load_seconds": round(load_seconds, 3),
        },
        "remap_rule": (
            "band lattice at export precision; see core/nlp/reranker.rerank_scores"
        ),
        "strategies": {name: report.as_dict() for name, report in reports.items()},
        "by_topic": by_topic,
        "timing": {
            "pairs_scored": pairs_scored,
            "inference_seconds": round(infer_seconds, 3),
            "ms_per_pair": round(ms_per_pair, 3),
            "model_load_seconds": round(load_seconds, 3),
            "note": (
                "quality per top_n is exact (a pair's score is independent of its "
                "neighbours, so the sweep shares one pass); the cost of a smaller "
                "top_n is top_n/N of the reported pairs, not separately clocked"
            ),
        },
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\n  artifact: {out_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
