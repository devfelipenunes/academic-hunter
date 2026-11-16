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
against it would describe nothing. The dense leg embeds through ChromaDB's
``DefaultEmbeddingFunction``, which is the function the pipeline's screener
already loads, for the same reason.

**Measured**, over the blockchain run, 25 questions:

| configuration                            | recall@10 | nDCG@10 | MRR    |
|------------------------------------------|-----------|---------|--------|
| BM25 alone (what the pipeline does today) | 0.7200    | 0.6203  | 0.5961 |
| + query-aware dense, 0.7/0.3              | 0.7200    | 0.6447  | 0.6328 |
| + reranker                                | 0.8400    | 0.6845  | 0.6420 |

The first version of this table was measured with ``sentence_transformers``
instead, which gave 0.6490 and 0.6845 — close enough that the conclusion holds,
but it described an embedding the pipeline never loads, so it was replaced
rather than kept. Two runtimes of the same model, and the difference is small;
that is worth knowing too.

**And the two instruments disagree.** Over the judged pool — 250 hand-graded
judgments, which is the better instrument — the dense leg dominates and the
blend is worse than dense alone:

| configuration              | pool nDCG@10 | questions nDCG@10 |
|----------------------------|--------------|-------------------|
| BM25 alone                 | 0.6654       | 0.6203            |
| dense + BM25, 0.7/0.3      | 0.7700       | 0.6447            |
| + reranker                 | 0.7989       | 0.6845            |
| dense alone, 0/1           | **0.8703**   | 0.5369            |

Dense beats BM25 on every one of the five pool queries, and by 0.65 on
``blockchain_governance_transparency`` — the one whose vocabulary ("government
transparency, accountability and anti-corruption") does not appear in the titles
of the papers that are relevant to it. That is the case dense retrieval exists
for.

The question set gives the opposite ordering, and it is the weaker instrument of
the two: its candidate pool *is* the 78 papers the pipeline included, so it is
selected by the score under test — the exact fault the salvaged pool's own
provenance note warns against — and its questions are written in Portuguese
against an English corpus, so BM25 matches mostly on the proper nouns inside
them. Neither has been reconciled, and until they are, no change to the ranking
should be justified by either alone.

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
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from academic_hunter.core.nlp.bm25 import BM25
from academic_hunter.core.nlp.fusion import fuse_scores
from academic_hunter.core.nlp.reranker import rerank_scores, rerank_texts
from academic_hunter.core.nlp.scorer import title_slug

DECIMALS = 1
CUTOFF = 10


def load_papers(run_dir: Path) -> List[Dict[str, Any]]:
    """Load a run's dataset or an explicit CSV, preserving its row order.

    Sorted and guarded. The glob's order is not defined, and ``[0]`` over an
    empty one was an ``IndexError`` raised from inside this file: on a fresh
    clone — where ``results/`` does not exist, because it is not versioned — the
    instrument that measures the pipeline died with a traceback naming neither
    the directory it had searched nor what a run puts there.
    """
    if run_dir.is_file():
        dataset = run_dir
    else:
        matches = sorted(glob.glob(str(run_dir / "academic_dataset_*.csv")))
        dataset = Path(matches[0]) if matches else None
    if dataset is None:
        raise FileNotFoundError(
            f"no academic_dataset_*.csv under {run_dir}. A run writes one into "
            f"results/run_<timestamp>/; point --run at such a directory, or at "
            f"tests/evaluation/fixtures/ for the run the qrels was measured on."
        )
    with dataset.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def document_text(paper: Dict[str, Any]) -> str:
    """What is embedded and what BM25 indexes: the same concatenation the step uses."""
    return f"{paper.get('Title', '')} {paper.get('Abstract', '')}"


def _embedder():
    """ChromaDB's ONNX embedding function — the one the pipeline already loads.

    Not ``sentence_transformers``, which is the same model by name in a second
    runtime with a second download. The pipeline's dense leg
    (``SemanticScreener``, via ``DefaultEmbeddingFunction``) never touches that
    one, so measuring with it described a configuration the pipeline cannot
    produce — and the first version of this harness did exactly that.
    """
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

    return DefaultEmbeddingFunction()


def _cosine(a: List[float], b: List[float]) -> float:
    """Clamped to ``[0, 1]`` the way ``SemanticScreener._cosine`` clamps it.

    Written out rather than done with numpy so this file needs no array library
    to say what it means: the two must agree, and the clamping is half of that.
    """
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a < 1e-10 or norm_b < 1e-10:
        return 0.0
    return max(0.0, dot / (norm_a * norm_b))


@lru_cache(maxsize=2)
def _embedded_corpus(texts: tuple[str, ...]):
    """Encode one corpus once per process, not once for every query."""
    embed = _embedder()
    vectors = embed(list(texts))
    return embed, tuple(tuple(float(x) for x in vector) for vector in vectors)


def query_dense_scores(texts: List[str], query: str) -> Optional[List[float]]:
    """Cosine between the question and each paper, or ``None`` without the model.

    This is the dense leg the literature means by hybrid search: it sees the
    question. The pipeline's own ``_sem_score`` does not — it is the cosine
    between the paper and a centroid of the *config's* terms, so it is the same
    number for every question asked of a fixed configuration. The two are not
    interchangeable, and telling them apart is what ``--dense`` is for.
    """
    try:
        embed, corpus_vectors = _embedded_corpus(tuple(texts))
        query_vector = [float(x) for x in embed([query])[0]]
    except Exception:  # noqa: BLE001
        return None
    return [_cosine(query_vector, list(vector)) for vector in corpus_vectors]


def rank_for_question(
    texts: List[str],
    question: str,
    *,
    weights: Optional[Dict[str, float]],
    dense: Optional[List[float]],
    rerank: bool,
    rerank_top_n: int,
    rerank_model: str,
    legs: Optional[Dict[str, Any]] = None,
) -> List[int]:
    """The order the pipeline would report for ``question``, best first.

    Mirrors :meth:`RecomputeRanksStep.run` and its rerank stage as they are
    written today: BM25 over the question as the sparse leg, the weighted-sum
    fusion at ``settings.fusion_weights``, and — when enabled — the cross-encoder
    over the head only, redistributing those scores rather than replacing them.

    ``legs`` is told whether the rerank actually applied. It is requested and it
    happens in two different places — ``rerank_texts`` returns ``None`` when the
    cross-encoder is missing, and the head can come back non-finite — so "the
    caller asked for it" is not the same fact as "it ran".
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
            if legs is not None:
                legs["rerank_ran"] = True
    return sorted(range(len(fused)), key=lambda i: (-fused[i], i))


def new_legs(args) -> Dict[str, Any]:
    """What was asked of each leg, before anything has run.

    ``dense_ran`` and ``rerank_ran`` are filled in by the callers, because they
    are facts about the run rather than about the request.
    """
    return {
        "dense_requested": args.dense == "query",
        "dense_ran": False,
        "rerank_requested": bool(args.rerank),
        "rerank_ran": False,
    }


def legs_line(result: Dict[str, Any]) -> str:
    """Which legs actually ran, in the output, next to the number they produced.

    A dense leg whose embedder will not load scores zero for every paper, and a
    rerank whose cross-encoder is missing is skipped outright — neither raises,
    and the metric prints the same as a measured one. This harness is what makes
    a change to the ranking argueable, so it cannot be where a leg goes quiet:
    the number below this line is only the number it claims to be if the legs it
    names are the legs that ran.
    """
    def describe(requested: bool, ran: bool) -> str:
        if not requested:
            return "off"
        return "ran" if ran else "REQUESTED BUT DID NOT RUN"

    return (
        f"  legs:  sparse=bm25  "
        f"dense={describe(result['dense_requested'], result['dense_ran'])}  "
        f"rerank={describe(result['rerank_requested'], result['rerank_ran'])}"
    )


def _weights_from(args) -> Dict[str, float]:
    """The fused weights, defaulting to what the step applies to a ranking query.

    Every query here *is* a ranking query, so with no weights given this
    reproduces that mode: the step drops the embedding to zero rather than
    falling back to ``DEFAULT_WEIGHTS`` (steps.py:214). Without it the baseline
    would be a scaling of the shipped ranking rather than the shipped ranking,
    and the rounded scores break ties differently.
    """
    if args.weights:
        keyword, embedding = (float(x) for x in args.weights.split(","))
        return {"keyword": keyword, "embedding": embedding}
    return {"keyword": 1.0, "embedding": 0.0}


def ndcg_at_k(ranked: List[int], grades: List[float], k: int = CUTOFF) -> float:
    """Graded nDCG@k, ``2**grade - 1`` being the gain.

    Graded rather than binary because the pool's judgments are: 0/1/2, read off
    title and abstract. Collapsing them to relevant/not would throw away the
    distinction between a paper that is on the topic and one that is the topic.
    """
    def dcg(order: List[int]) -> float:
        return sum(
            (2.0 ** grades[i] - 1.0) / math.log2(position + 2)
            for position, i in enumerate(order[:k])
        )

    ideal = sorted(range(len(grades)), key=lambda i: -grades[i])
    best = dcg(ideal)
    return dcg(ranked) / best if best > 0 else 0.0


def evaluate_pool(pool_path: Path, args) -> Dict[str, Any]:
    """Score a judged pool: rank its fixed candidate set and grade the order.

    A different question from ``evaluate``. There the corpus is whatever run the
    dataset holds and the metric asks whether the right paper was found at all;
    here the candidates are fixed at 50 and the metric asks only how well they
    were ordered. That is what a change to fusion or reranking moves, and it is
    the only thing this pool can still measure — the 1538-paper corpus it was
    drawn from is gone, and never was in git.
    """
    data = json.loads(pool_path.read_text())
    documents = data["documents"]
    weights = _weights_from(args)
    legs = new_legs(args)

    per_query, ndcgs = [], []
    for name, query in data["queries"].items():
        ids = query["pool"]
        texts = [
            f"{documents[i].get('title', '')} {documents[i].get('abstract', '')}"
            for i in ids
        ]
        grades = [float((query["judgments"] or {}).get(i, 0)) for i in ids]

        dense = query_dense_scores(texts, query["text"]) if args.dense == "query" else None
        if dense is not None:
            legs["dense_ran"] = True
        order = rank_for_question(
            texts, query["text"], weights=weights, dense=dense,
            rerank=args.rerank, rerank_top_n=args.top_n,
            rerank_model=args.rerank_model, legs=legs,
        )
        score = ndcg_at_k(order, grades)
        ndcgs.append(score)
        per_query.append({
            "query": name,
            "text": query["text"],
            "ndcg@10": score,
            "best_ranked": documents[ids[order[0]]].get("title", "")[:70],
            "best_judged": documents[ids[grades.index(max(grades))]].get("title", "")[:70],
        })

    return {
        "mode": "pool",
        "queries": len(ndcgs),
        "candidates": len(next(iter(data["queries"].values()))["pool"]),
        "ndcg@10": sum(ndcgs) / len(ndcgs) if ndcgs else 0.0,
        **legs,
        "per_query": per_query,
    }


def evaluate(run_dir: Path, qrels: Dict[str, Any], args) -> Dict[str, Any]:
    papers = load_papers(run_dir)
    texts = [document_text(p) for p in papers]
    by_doi = {(p.get("DOI") or "").strip().lower(): i for i, p in enumerate(papers)}
    by_slug = {title_slug(p.get("Title", "")): i for i, p in enumerate(papers)}

    weights = _weights_from(args)
    legs = new_legs(args)

    per_question = []
    for item in qrels["questions"]:
        target = by_doi.get(item["target_doi"]) if item["target_doi"] else None
        if target is None:
            target = by_slug.get(item["target_slug"])
        if target is None:
            per_question.append({"question": item["question"], "rank": None,
                                 "note": "target missing from the run"})
            continue

        dense = None
        if args.dense == "query":
            dense = query_dense_scores(texts, item["question"])
            if dense is not None:
                legs["dense_ran"] = True

        order = rank_for_question(
            texts, item["question"], weights=weights, dense=dense,
            rerank=args.rerank, rerank_top_n=args.top_n,
            rerank_model=args.rerank_model, legs=legs,
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
        **legs,
        "per_question": per_question,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Retrieval quality over a saved run.")
    parser.add_argument("--run", type=Path, default=None,
                        help="saved run directory containing academic_dataset_*.csv")
    parser.add_argument("--dataset", type=Path, default=None,
                        help="explicit CSV dataset (for a review corpus or benchmark fixture)")
    parser.add_argument("--qrels", type=Path, default=None)
    parser.add_argument("--pool", type=Path, default=None,
                        help="a judged pool: rank its fixed candidates and grade the order")
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

    if not args.pool and not ((args.run or args.dataset) and args.qrels):
        parser.error("give either --pool, or --qrels with --run or --dataset")
    if args.run and args.dataset:
        parser.error("use only one of --run and --dataset")

    label = f"weights={args.weights or 'default'} dense={args.dense} rerank={args.rerank}"
    try:
        result = _run(args, label)
    except FileNotFoundError as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 1
    if args.json:
        args.json.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def _run(args, label: str) -> Dict[str, Any]:
    """Run the requested mode and print it.

    Separated so ``main`` can turn a missing dataset into one readable line: the
    message ``load_papers`` raises is the whole point of raising it, and a
    traceback stacked under it buries it.
    """
    if args.pool:
        result = evaluate_pool(args.pool, args)
        print(f"\n{args.pool.name}  |  pool  |  {label}")
        print(f"  queries {result['queries']}  candidates per query {result['candidates']}")
        print(f"  nDCG@10 {result['ndcg@10']:.4f}")
        print(legs_line(result))
        for q in result["per_query"]:
            print(f"    {q['ndcg@10']:.4f}  {q['query']}")
            if args.verbose:
                print(f"            ranked 1  {q['best_ranked']}")
                print(f"            best      {q['best_judged']}")
    else:
        qrels = json.loads(args.qrels.read_text())
        dataset = args.dataset or args.run
        result = evaluate(dataset, qrels, args)
        print(f"\n{dataset.name}  |  {label}")
        print(f"  questions {result['questions']}"
              f"  (with their target in the run: {result['answered']})")
        print(f"  recall@10 {result['recall@10']:.4f}   nDCG@10 {result['ndcg@10']:.4f}"
              f"   MRR {result['mrr']:.4f}   median rank {result['median_rank']}")
        print(legs_line(result))
        if result["answered"] == 0:
            print(
                "  !  none of the qrels' targets is in this run, so these metrics "
                "compare nothing.\n"
                f"     The qrels was written against {qrels.get('run', '?')}; point "
                "--run at that run, or leave it unset for the versioned fixture."
            )
        elif result["answered"] < result["questions"]:
            print(
                f"  !  {result['questions'] - result['answered']} of the qrels' targets "
                "is not in this run; the metrics are computed over all "
                f"{result['questions']} questions regardless."
            )
        if args.verbose:
            for q in result["per_question"]:
                print(f"    {q['rank'] or '-':>4}  {q['question'][:70]}")
    return result


if __name__ == "__main__":
    sys.exit(main())
