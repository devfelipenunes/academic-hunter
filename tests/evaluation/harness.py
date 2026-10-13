"""Measure retrieval over a run that already exists, without touching the network.

Twenty-five questions whose answer is one known paper of the corpus, and the
ranked list the pipeline would produce for each. ``recall@10`` is "in how many
questions is the right paper in the top ten"; ``nDCG@10`` is the same thing
weighted by how high it landed.

The point is the before/after pair. A change to the ranking that has no number
on either side of it is an opinion, and this project has already paid for one of
those: two measurements live in the prose of
:mod:`academic_hunter.core.pipeline.steps` and the data behind them left with
``evaluation/``, so nothing today distinguishes "measured and rejected" from
"never ran".

It runs on a saved run, not on a fresh search: no credits, no rate limits, and
the same answer every time.

Every ranking rule here is the shipped one — ``BM25``, ``fuse_scores``,
``rerank_texts``, ``rerank_scores`` — called, never reimplemented. A second
implementation is free to drift from the one that runs, and a measurement taken
against it would describe nothing.

Usage::

    venv/bin/python tests/evaluation/harness.py \
        --run results/run_20261013_093241 \
        --qrels tests/evaluation/qrels_blockchain.json \
        --weights 1,0
"""

import argparse
import csv
import glob
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from academic_hunter.core.nlp.bm25 import BM25
from academic_hunter.core.nlp.fusion import fuse_scores
from academic_hunter.core.nlp.model_cache import get_sentence_transformer
from academic_hunter.core.nlp.reranker import rerank_scores, rerank_texts
from academic_hunter.core.nlp.scorer import title_slug

DECIMALS = 1
CUTOFF = 10


def load_papers(run_dir: Path) -> List[Dict[str, Any]]:
    """The run's dataset, in the order it was written."""
    path = glob.glob(str(run_dir / "academic_dataset_*.csv"))[0]
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def document_text(paper: Dict[str, Any]) -> str:
    """What is embedded and what BM25 indexes: the same concatenation the step uses."""
    return f"{paper.get('Title', '')} {paper.get('Abstract', '')}"


def query_dense_scores(texts: List[str], query: str) -> Optional[List[float]]:
    """Cosine between the question and each paper, or ``None`` without the model.

    This is the dense leg the literature means by hybrid search: it sees the
    question. The pipeline's own ``_sem_score`` does not — it is the cosine
    between the paper and a centroid of the *config's* terms, so it is the same
    number for every question asked of a fixed configuration. The two are not
    interchangeable, and telling them apart is what ``--dense`` is for.
    """
    model = get_sentence_transformer()
    if model is None:
        return None
    vectors = model.encode([query] + texts, normalize_embeddings=True)
    query_vector = vectors[0]
    return [float(query_vector @ vector) for vector in vectors[1:]]


def rank_for_question(
    texts: List[str],
    question: str,
    *,
    weights: Optional[Dict[str, float]],
    dense: Optional[List[float]],
    rerank: bool,
    rerank_top_n: int,
    rerank_model: str,
) -> List[int]:
    """The order the pipeline would report for ``question``, best first.

    Mirrors :meth:`RecomputeRanksStep.run` and its rerank stage as they are
    written today: BM25 over the question as the sparse leg, the weighted-sum
    fusion at ``settings.fusion_weights``, and — when enabled — the cross-encoder
    over the head only, redistributing those scores rather than replacing them.
    """
    sparse = BM25(texts).score(question)
    dense = dense if dense is not None else [0.0] * len(texts)

    fused = fuse_scores(sparse, dense, strategy="weighted_norm",
                        weights=weights, cit_scores=None)
    fused = [round(float(s), DECIMALS) for s in fused]

    if rerank:
        head = sorted(range(len(fused)), key=lambda i: (-fused[i], i))[:rerank_top_n]
        scores = rerank_texts(question, [texts[i] for i in head], model_name=rerank_model)
        if scores is not None and all(math.isfinite(s) for s in scores):
            order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
            fused = rerank_scores(fused, [head[i] for i in order], DECIMALS)
    return sorted(range(len(fused)), key=lambda i: (-fused[i], i))


def evaluate(run_dir: Path, qrels: Dict[str, Any], args) -> Dict[str, Any]:
    papers = load_papers(run_dir)
    texts = [document_text(p) for p in papers]
    by_doi = {(p.get("DOI") or "").strip().lower(): i for i, p in enumerate(papers)}
    by_slug = {title_slug(p.get("Title", "")): i for i, p in enumerate(papers)}

    # Every question here *is* a ranking query, so with no weights given this
    # reproduces what the step does in that mode: it drops the embedding to zero
    # rather than falling back to `DEFAULT_WEIGHTS` (steps.py:214). Without this
    # the baseline would be a scaling of the shipped ranking rather than the
    # shipped ranking, and the rounded scores break ties differently.
    if args.weights:
        keyword, embedding = (float(x) for x in args.weights.split(","))
        weights: Optional[Dict[str, float]] = {"keyword": keyword, "embedding": embedding}
    else:
        weights = {"keyword": 1.0, "embedding": 0.0}

    per_question = []
    for item in qrels["questions"]:
        target = by_doi.get(item["target_doi"]) if item["target_doi"] else None
        if target is None:
            target = by_slug.get(item["target_slug"])
        if target is None:
            per_question.append({"question": item["question"], "rank": None,
                                 "note": "alvo ausente do run"})
            continue

        dense = None
        if args.dense == "query":
            dense = query_dense_scores(texts, item["question"])

        order = rank_for_question(
            texts, item["question"], weights=weights, dense=dense,
            rerank=args.rerank, rerank_top_n=args.top_n,
            rerank_model=args.rerank_model,
        )
        rank = order.index(target) + 1
        per_question.append({
            "question": item["question"],
            "target_title": item["target_title"],
            "rank": rank,
        })

    ranks = [q["rank"] for q in per_question if q["rank"]]
    n = len(per_question)
    hits = [r for r in ranks if r <= CUTOFF]
    return {
        "questions": n,
        "answered": len(ranks),
        "recall@10": len(hits) / n if n else 0.0,
        "ndcg@10": sum(1.0 / math.log2(r + 1) for r in hits) / n if n else 0.0,
        "mrr": sum(1.0 / r for r in ranks) / n if n else 0.0,
        "median_rank": sorted(ranks)[len(ranks) // 2] if ranks else None,
        "per_question": per_question,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Retrieval quality over a saved run.")
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--qrels", required=True, type=Path)
    parser.add_argument("--weights", default=None,
                        help="keyword,embedding — fused weights, e.g. '1,0' or '0.7,0.3'")
    parser.add_argument("--dense", default="none", choices=["none", "query"],
                        help="'query' embeds the question; 'none' leaves the dense leg at zero")
    parser.add_argument("--rerank", action="store_true")
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--rerank-model", default="cross-encoder/ms-marco-MiniLM-L-6-v2")
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    qrels = json.loads(args.qrels.read_text())
    result = evaluate(args.run, qrels, args)

    label = f"weights={args.weights or 'default'} dense={args.dense} rerank={args.rerank}"
    print(f"\n{args.run.name}  |  {label}")
    print(f"  perguntas {result['questions']}  (com alvo no run: {result['answered']})")
    print(f"  recall@10 {result['recall@10']:.4f}   nDCG@10 {result['ndcg@10']:.4f}"
          f"   MRR {result['mrr']:.4f}   mediana da posicao {result['median_rank']}")
    if args.verbose:
        for q in result["per_question"]:
            print(f"    {q['rank'] or '-':>4}  {q['question'][:70]}")
    if args.json:
        args.json.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
