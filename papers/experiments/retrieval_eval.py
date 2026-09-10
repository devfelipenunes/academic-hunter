#!/usr/bin/env python3
"""Score retrieval strategies against a judged collection.

This is the criterion of success the roadmap was missing: until a retrieval
change can be measured against human judgments, "the new embedding is better"
is unfalsifiable.

What it measures — and what it does not
---------------------------------------
Each query is ranked over the **judged pool only**, i.e. the documents that
carry a relevance grade. Every candidate is therefore judged, so the metrics
compare rankers cleanly instead of being depressed by unjudged documents the
pool never covered.

The consequence is that this measures *ranking* quality over a fixed candidate
set, not recall from the full corpus. A retriever that would have found great
documents outside the pool gets no credit for them, and one ranking the pool
perfectly scores 1.0 regardless of what it missed elsewhere. Growing the pool
(and judging more of it) is what extends the claim from "ranks well" to
"retrieves well". :func:`judged_coverage` in the report keeps that limit
visible.

Usage:
    python papers/experiments/retrieval_eval.py
    python papers/experiments/retrieval_eval.py --with-embedding
    python papers/experiments/retrieval_eval.py --qrels path/to/qrels.json
"""

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from academic_hunter.core.evaluation import build_rankings, evaluate_run, load_qrels
from academic_hunter.core.evaluation.qrels import doc_id_for
from academic_hunter.core.infra import HunterConfig
from academic_hunter.core.nlp import AcademicScorer

RESULTS_DIR = Path(__file__).parent / "results"
DEFAULT_QRELS = ROOT / "papers" / "evaluation" / "qrels_pilot_genre_analysis.json"
KS = (5, 10, 20)


def load_pool(qrels_path: Path) -> tuple[list, str]:
    """Load the judged pool.

    Prefers the documents embedded in the qrels file. The corpus lives under
    ``results/``, which is git-ignored, so a qrels that only recorded a CSV path
    would be unusable on a fresh clone — the judged set has to travel with its
    own documents. The CSV path is kept as provenance and as a fallback for
    extending the collection locally.

    Every returned document carries ``_doc_id``, and only judged documents are
    returned: the pool is defined by the judgments, so all candidates are
    judged and the metrics compare rankers rather than pool coverage.
    """
    payload = json.loads(qrels_path.read_text(encoding="utf-8"))
    judged = {
        doc_id for query in payload["queries"].values() for doc_id in query["judgments"]
    }

    embedded = payload.get("documents")
    if embedded:
        pool = [
            {
                "_doc_id": doc_id,
                "Title": doc.get("title", ""),
                "Abstract": doc.get("abstract", ""),
                "Year": doc.get("year"),
                "Source": doc.get("source"),
                "Citations": doc.get("citations"),
                "Relevance_Score": doc.get("pipeline_relevance_score"),
            }
            for doc_id, doc in embedded.items()
            if doc_id in judged
        ]
        missing = judged - {d["_doc_id"] for d in pool}
        if missing:
            raise SystemExit(
                f"{len(missing)} judged document(s) have no embedded entry, e.g. "
                f"{sorted(missing)[:2]}. The judgments and the documents have diverged."
            )
        return pool, f"embedded ({len(pool)} documents)"

    source_csv = payload.get("provenance", {}).get("source_csv")
    if not source_csv:
        raise SystemExit(
            f"{qrels_path} has neither an embedded 'documents' map nor "
            "'provenance.source_csv', so the judged documents cannot be recovered."
        )

    csv_path = ROOT / source_csv if not Path(source_csv).is_absolute() else Path(source_csv)
    if not csv_path.exists():
        raise SystemExit(
            f"{csv_path} not found. This qrels predates the embedded document map "
            "and its corpus is not in version control."
        )

    rows = list(csv.DictReader(open(csv_path, encoding="utf-8", errors="replace")))
    pool = []
    for r in rows:
        doc_id = doc_id_for(r.get("Title", ""), r.get("DOI", ""))
        if doc_id in judged:
            r["_doc_id"] = doc_id
            pool.append(r)

    missing = judged - {d["_doc_id"] for d in pool}
    if missing:
        raise SystemExit(
            f"{len(missing)} judged document(s) are not in {source_csv}, e.g. "
            f"{sorted(missing)[:2]}. The pool and the judgments have diverged."
        )

    return pool, str(csv_path.relative_to(ROOT))


def build_scorers(config: HunterConfig, with_embedding: bool) -> dict:
    """Return name -> ``scorer(document, query_text) -> float``.

    All scorers except the embedding one are deterministic and offline.
    """
    scorer = AcademicScorer(
        config.anchors, config.tech_strings,
        config.tech_weights, config.context_rules, config.settings,
    )

    def reported(doc, _query):
        """The score the run exported, as a *reference point only*.

        Caveat: its ranks were computed over the full run (hundreds of papers),
        while this evaluation ranks only the judged pool. The two are not
        comparable, and this row tends to look far worse than the rule that
        produced it. Use ``fusion_comparison.py`` to compare fusion rules — it
        recomputes the ranks over the pool, which is the like-for-like test.
        """
        return float(doc.get("Relevance_Score") or 0.0)

    def keyword(doc, _query):
        """Anchor/technical-term weighting, ignoring the query text."""
        return scorer.calculate_score(
            doc.get("Title", ""), doc.get("Abstract", ""),
            int(doc.get("Citations") or 0),
        )

    def citations(doc, _query):
        """A deliberately naive baseline: most-cited first."""
        return float(doc.get("Citations") or 0)

    scorers = {
        "exported_score (see note)": reported,
        "keyword": keyword,
        "citations_baseline": citations,
    }

    if with_embedding:
        from academic_hunter.plugins.screeners import SemanticScreener

        screener = SemanticScreener()
        sem_config = config.screener_config()

        def embedding(doc, _query):
            """Weight-Bleeding centroid similarity."""
            return screener.evaluate(doc, sem_config)

        scorers["embedding"] = embedding

    return scorers


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qrels", default=str(DEFAULT_QRELS), help="judged collection")
    parser.add_argument(
        "--with-embedding", action="store_true",
        help="also score with the Weight-Bleeding embedding (loads MiniLM)",
    )
    args = parser.parse_args()

    qrels_path = Path(args.qrels)
    qrels = load_qrels(qrels_path)
    pool, csv_label = load_pool(qrels_path)

    config = HunterConfig()
    scorers = build_scorers(config, args.with_embedding)

    queries = {qid: j.text for qid, j in qrels.queries.items()}

    print("=" * 72)
    print("  Retrieval evaluation")
    print("=" * 72)
    stats = qrels.stats()
    print(f"  qrels      : {qrels_path.relative_to(ROOT)}")
    print(f"  pool       : {csv_label}")
    print(f"  pool size  : {len(pool)} judged documents")
    print(f"  queries    : {stats['queries']}   judgments: {stats['judgments']}   "
          f"relevant: {stats['relevant']}")
    print()

    reports = {}
    for name, scorer in scorers.items():
        rankings = build_rankings(
            pool, queries, scorer=scorer,
            doc_id=lambda d: d["_doc_id"],
            top_k=len(pool),
        )
        report = evaluate_run(qrels, rankings, ks=KS)
        reports[name] = report

    # ── comparison table ────────────────────────────────────────────────────
    metric_cols = [f"ndcg@{k}" for k in KS] + ["mrr", "ap"]
    header = f"  {'strategy':<22}" + "".join(f"{c:>10}" for c in metric_cols)
    print(header)
    print("  " + "-" * (len(header) - 2))

    for name, report in reports.items():
        row = f"  {name:<22}"
        for col in metric_cols:
            value = report.mean.get(col)
            row += f"{value:>10.4f}" if value is not None else f"{'n/a':>10}"
        print(row)

    print()
    print("  note: 'exported_score' is the run's own Relevance_Score. Its ranks")
    print("        were computed over the full run, not over this pool, so it is")
    print("        a reference point and not a like-for-like comparison.")
    print()

    best = max(reports.items(), key=lambda kv: kv[1].mean.get("ndcg@10", 0.0))
    baseline = reports.get("citations_baseline")
    if baseline is not None:
        delta = best[1].mean.get("ndcg@10", 0.0) - baseline.mean.get("ndcg@10", 0.0)
        print(f"  best strategy: {best[0]} (nDCG@10 {best[1].mean.get('ndcg@10', 0):.4f})")
        print(f"  nDCG@10 over the citation baseline: {delta:+.4f}")
    print(f"  min judged coverage: {min(r.min_coverage for r in reports.values()):.2f} "
          f"(every pool document is judged, so this should be 1.00)")

    # ── per-query detail for the best strategy ──────────────────────────────
    print()
    print(f"  Per-query detail ({best[0]}):")
    for qid, metrics in sorted(best[1].per_query.items()):
        print(f"    {qid:<26} nDCG@10={metrics.get('ndcg@10', 0):.4f}  "
              f"recall@10={metrics.get('recall@10', 0):.4f}  "
              f"AP={metrics.get('ap', 0):.4f}")

    out = RESULTS_DIR / "retrieval_eval.json"
    RESULTS_DIR.mkdir(exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "qrels": str(qrels_path.relative_to(ROOT)),
                "pool": csv_label,
                "pool_size": len(pool),
                "ks": list(KS),
                "qrels_stats": stats,
                "strategies": {name: report.as_dict() for name, report in reports.items()},
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\n✅ Results saved to {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
