"""Score a ranked result set against a judged collection."""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Sequence

from .metrics import DEFAULT_KS, evaluate_ranking, mean_metrics
from .qrels import Qrels, pooled_documents, relevance_map


@dataclass
class Ranking:
    """One query's ranked document ids, most relevant first."""

    query_id: str
    doc_ids: List[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.doc_ids)


@dataclass
class EvaluationReport:
    """Per-query metrics plus their mean and the judgments they rest on."""

    mean: Dict[str, float]
    per_query: Dict[str, Dict[str, float]]
    n_queries: int
    n_judgments: int
    n_relevant: int
    #: Query id -> fraction of the top-k retrieved documents that carry a judgment.
    judged_coverage: Dict[str, float] = field(default_factory=dict)

    @property
    def min_coverage(self) -> float:
        """Lowest per-query judged coverage — the report's weakest link."""
        return min(self.judged_coverage.values()) if self.judged_coverage else 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "n_queries": self.n_queries,
            "n_judgments": self.n_judgments,
            "n_relevant": self.n_relevant,
            "mean": self.mean,
            "per_query": self.per_query,
            "judged_coverage": self.judged_coverage,
            "min_coverage": self.min_coverage,
        }


def evaluate_run(
    qrels: Qrels,
    rankings: Mapping[str, Sequence[str]],
    ks: Sequence[int] = DEFAULT_KS,
    linear_gain: bool = False,
) -> EvaluationReport:
    """Compute metrics for every judged query that has a ranking.

    Queries present in the qrels but missing from ``rankings`` are skipped — a
    retriever that returns nothing for a query should be recorded as such by the
    caller, not silently scored as zero here.

    Args:
        qrels: The judged collection.
        rankings: Query id -> ranked document ids.
        ks: Rank cutoffs to report.
        linear_gain: Use raw grades rather than ``2^grade - 1``.

    Returns:
        An :class:`EvaluationReport` with per-query and mean metrics.
    """
    ks = sorted({int(k) for k in ks if int(k) > 0})
    top_k = max(ks) if ks else 0

    per_query: Dict[str, Dict[str, float]] = {}
    coverage: Dict[str, float] = {}

    for query_id, judgment in qrels.queries.items():
        if query_id not in rankings:
            continue

        ranking = list(rankings[query_id])
        relevance = relevance_map(qrels, query_id)
        per_query[query_id] = evaluate_ranking(
            ranking, relevance, ks=ks, linear_gain=linear_gain
        )

        if top_k:
            top = ranking[:top_k]
            # A document with no judgment cannot contribute relevance, so a
            # ranking full of unjudged documents produces a number that says
            # more about the qrels than about the retriever.
            judged = sum(1 for d in top if d in relevance)
            coverage[query_id] = judged / len(top) if top else 0.0

    return EvaluationReport(
        mean=mean_metrics(list(per_query.values())),
        per_query=per_query,
        n_queries=len(per_query),
        n_judgments=qrels.n_judgments,
        n_relevant=qrels.n_relevant,
        judged_coverage=coverage,
    )


def build_rankings(
    corpus: Sequence[Any],
    queries: Mapping[str, str],
    scorer: Callable[[Any, str], float],
    doc_id: Callable[[Any], str],
    top_k: int = 100,
) -> Dict[str, List[str]]:
    """Rank a fixed corpus for each query using a scoring callable.

    The corpus is held constant across queries so that differences in the
    metrics come from the scorer and not from a different candidate set.

    Args:
        corpus: Documents to rank.
        queries: Query id -> query text.
        scorer: ``scorer(document, query_text) -> float``, higher is better.
        doc_id: ``doc_id(document) -> str``, matching the qrels ids.
        top_k: Keep only the top ``top_k`` documents per query.

    Returns:
        Query id -> ranked document ids.
    """
    rankings: Dict[str, List[str]] = {}
    for query_id, text in queries.items():
        scored = [(scorer(doc, text), doc_id(doc)) for doc in corpus]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        rankings[query_id] = [d for _, d in scored[:top_k]]
    return rankings


def unjudged_in_pool(qrels: Qrels, pool: Sequence[str]) -> set:
    """Pooled documents that carry no judgment in the qrels.

    Useful when building the collection: a pool much larger than the judged set
    means most retrieved documents will be unjudged.
    """
    return set(pool) - pooled_documents(qrels)
