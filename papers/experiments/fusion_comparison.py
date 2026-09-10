#!/usr/bin/env python3
"""Compare fusion strategies for the two retrieval signals.

``RecomputeRanksStep`` combines the keyword score and the Weight-Bleeding score
into ``Relevance_Score``. It used to do so as a geometric mean of percentile
ranks::

    score = sqrt(rank_kw * rank_sem) * 10

There was no way to tell whether that was any good until a judged collection
existed. It exists now (``papers/evaluation``), and it said the rank-geometric
rule measured *worse than either of its own inputs*: flattening both signals to
percentile ranks before combining discards magnitude, so a paper far ahead on
one signal and mid-pack on the other becomes indistinguishable from one that is
mediocre on both.

The shipped rule is now a weighted sum of min-max normalised scores
(``core.nlp.fuse_scores``). On 6 queries / 58 judged documents, nDCG@10:

    keyword_only .......... 0.3952
    shipped (weighted_norm)  0.3934   <- 70% keyword + 30% embedding
    min_rank .............. 0.3335
    shipped (rank_geometric) 0.3175   <- the superseded rule
    rrf_60 ................ 0.3117
    embedding_only ........ 0.2860
    citations_baseline .... 0.1084

Two things worth keeping in mind. The shipped rules are evaluated by calling
``fuse_scores`` itself, so the experiment cannot drift from the code. And note
that **RRF — the roadmap's suggestion — is among the worst**: it merges rank
*positions* on the assumption that the two lists contain different documents,
whereas here they are two orderings of the same set, so its damping discards
signal instead of combining it.

This script holds the signals fixed and varies only the fusion, so any
difference is attributable to the combination rule and not to the components.

Usage:
    python papers/experiments/fusion_comparison.py
    python papers/experiments/fusion_comparison.py --qrels path/to/qrels.json
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from academic_hunter.core.evaluation import documents_for, evaluate_run, load_qrels, mean_metrics, topics
from academic_hunter.core.infra import HunterConfig
from academic_hunter.core.nlp import AcademicScorer, fuse_scores

RESULTS_DIR = Path(__file__).parent / "results"
DEFAULT_QRELS = ROOT / "papers" / "evaluation" / "qrels_pilot_genre_analysis.json"
KS = (5, 10, 20)


def load_documents(qrels_path: Path) -> dict:
    """Every judged document, keyed by id, in the shape the scorers expect."""
    payload = json.loads(qrels_path.read_text(encoding="utf-8"))
    return {
        doc_id: {
            "_doc_id": doc_id,
            "Title": doc.get("title", ""),
            "Abstract": doc.get("abstract", ""),
            "Citations": doc.get("citations"),
            "Relevance_Score": doc.get("pipeline_relevance_score"),
        }
        for doc_id, doc in payload["documents"].items()
    }


def percentile_ranks(values: list) -> list:
    """Percentile rank of each value, matching RecomputeRanksStep.

    Ties share the position of the last of their group, which is what
    ``argsort``-based rank assignment produces in the pipeline.
    """
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    n = len(values)
    for position, index in enumerate(order):
        ranks[index] = position / max(n - 1, 1)
    return ranks


def position_ranks(values: list) -> list:
    """1-based rank position, for RRF. Ties broken by original order."""
    order = sorted(range(len(values)), key=lambda i: -values[i])
    ranks = [0] * len(values)
    for position, index in enumerate(order, start=1):
        ranks[index] = position
    return ranks


def minmax(values: list) -> list:
    """Min-max normalisation to [0, 1]; constant input maps to 0."""
    lo, hi = min(values), max(values)
    if hi - lo == 0:
        return [0.0] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qrels", default=str(DEFAULT_QRELS))
    parser.add_argument("--rrf-k", type=int, default=60, help="RRF damping constant")
    args = parser.parse_args()

    qrels_path = Path(args.qrels)
    qrels = load_qrels(qrels_path)
    documents = load_documents(qrels_path)

    config = HunterConfig()
    scorer = AcademicScorer(
        config.anchors, config.tech_strings,
        config.tech_weights, config.context_rules, config.settings,
    )

    from academic_hunter.plugins.screeners import SemanticScreener

    screener = SemanticScreener()
    sem_config = config.screener_config()

    import math

    by_topic = topics(qrels)

    def fusions_for(corpus):
        """Every candidate rule, computed over one topic's candidate set.

        Ranks and min-max normalisation are relative to the candidate set, so
        they must be computed per pool — fusing across two topics would rank a
        document against documents it is never competing with.
        """
        kw = [
            scorer.calculate_score(
                d.get("Title", ""), d.get("Abstract", ""), int(d.get("Citations") or 0)
            )
            for d in corpus
        ]
        sem = [screener.evaluate(d, sem_config) for d in corpus]
        citations = [float(d.get("Citations") or 0) for d in corpus]

        r_kw, r_sem = percentile_ranks(kw), percentile_ranks(sem)
        p_kw, p_sem = position_ranks(kw), position_ranks(sem)
        n_kw, n_sem = minmax(kw), minmax(sem)

        return {
            "keyword_only": kw,
            "embedding_only": sem,
            "citations_baseline": citations,
            # ── the rules the pipeline actually ships, via the shared function.
            #    Reimplementing them here would let the experiment drift from
            #    the code and quietly stop measuring it. ──
            "shipped (weighted_norm)": fuse_scores(kw, sem),
            "shipped (rank_geometric)": fuse_scores(kw, sem, strategy="rank_geometric"),
            # ── alternatives that are not shipped, for comparison ──
            "arith_rank": [(a + b) / 2.0 * 10.0 for a, b in zip(r_kw, r_sem)],
            "min_rank": [min(a, b) * 10.0 for a, b in zip(r_kw, r_sem)],
            "max_rank": [max(a, b) * 10.0 for a, b in zip(r_kw, r_sem)],
            f"rrf_{args.rrf_k}": [
                1.0 / (args.rrf_k + a) + 1.0 / (args.rrf_k + b)
                for a, b in zip(p_kw, p_sem)
            ],
            "weighted_norm_50_50": [0.5 * a + 0.5 * b for a, b in zip(n_kw, n_sem)],
        }

    # topic -> (doc_ids, fusion name -> scores)
    per_topic = {}
    for topic, qids in by_topic.items():
        doc_ids = [d for d in documents_for(qrels, qids[0]) if d in documents]
        corpus = [documents[d] for d in doc_ids]
        per_topic[topic] = (doc_ids, fusions_for(corpus))

    stats = qrels.stats()
    print("=" * 78)
    print("  Fusion comparison — same signals, different combination rules")
    print("=" * 78)
    print(f"  documents: {len(documents)} judged | queries: {stats['queries']} | "
          f"judgments: {stats['judgments']} | relevant: {stats['relevant']}")
    for topic, (doc_ids, _) in per_topic.items():
        print(f"    {topic or '(sem tópico)':<24} pool de {len(doc_ids)} documentos")
    print()

    fusion_names = list(next(iter(per_topic.values()))[1])
    reports = {}
    for name in fusion_names:
        rankings = {}
        for topic, qids in by_topic.items():
            doc_ids, scores = per_topic[topic]
            order = sorted(range(len(doc_ids)), key=lambda i: -scores[name][i])
            ranking = [doc_ids[i] for i in order]
            for qid in qids:
                rankings[qid] = ranking
        reports[name] = evaluate_run(qrels, rankings, ks=KS)

    cols = [f"ndcg@{k}" for k in KS] + ["mrr", "ap"]
    header = f"  {'fusion':<22}" + "".join(f"{c:>10}" for c in cols)
    print(header)
    print("  " + "-" * (len(header) - 2))

    ranked = sorted(reports.items(), key=lambda kv: -kv[1].mean.get("ndcg@10", 0.0))
    for name, report in ranked:
        row = f"  {name:<22}"
        for col in cols:
            value = report.mean.get(col)
            row += f"{value:>10.4f}" if value is not None else f"{'n/a':>10}"
        print(row)

    print()
    current = reports["shipped (rank_geometric)"].mean.get("ndcg@10", 0.0)
    winner_name, winner = ranked[0]
    print(f"  best  : {winner_name}  nDCG@10 {winner.mean.get('ndcg@10', 0):.4f}")
    print(f"  current: shipped (rank_geometric)  nDCG@10 {current:.4f}")
    print(f"  delta : {winner.mean.get('ndcg@10', 0) - current:+.4f} nDCG@10")

    out = RESULTS_DIR / "fusion_comparison.json"
    RESULTS_DIR.mkdir(exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "qrels": str(qrels_path.relative_to(ROOT)),
                "document_count": len(documents),
                "pools": {topic: len(ids) for topic, (ids, _) in per_topic.items()},
                "ks": list(KS),
                "rrf_k": args.rrf_k,
                "results": {name: r.as_dict() for name, r in reports.items()},
                "ranking_by_ndcg10": [name for name, _ in ranked],
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
