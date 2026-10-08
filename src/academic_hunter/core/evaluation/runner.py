"""Score a ranked result set against a judged collection."""

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Sequence, Tuple

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
        An :class:`EvaluationReport` with per-query and mean metrics. Its
        ``n_judgments`` and ``n_relevant`` count the queries that were scored,
        not the whole collection: a report over a subset of the qrels reported
        the *collection's* judgment totals beside a per-query mean computed from
        a handful of them, and the two denominators cannot both be right.
    """
    ks = sorted({int(k) for k in ks if int(k) > 0})
    top_k = max(ks) if ks else 0

    per_query: Dict[str, Dict[str, float]] = {}
    coverage: Dict[str, float] = {}
    n_judgments = 0
    n_relevant = 0

    for query_id, judgment in qrels.queries.items():
        if query_id not in rankings:
            continue

        n_judgments += len(judgment)
        n_relevant += len(judgment.relevant_ids)

        ranking = list(rankings[query_id])
        relevance = relevance_map(qrels, query_id)
        per_query[query_id] = evaluate_ranking(
            ranking, relevance, ks=ks, linear_gain=linear_gain
        )

        if top_k:
            top = ranking[:top_k]
            judged = sum(1 for d in top if d in relevance)
            coverage[query_id] = judged / len(top) if top else 0.0

    return EvaluationReport(
        mean=mean_metrics(list(per_query.values())),
        per_query=per_query,
        n_queries=len(per_query),
        n_judgments=n_judgments,
        n_relevant=n_relevant,
        judged_coverage=coverage,
    )


def _require_non_negative(top_k: int) -> None:
    """A negative limit reaches the slice as an index, not as a limit.

    ``scored[:-1]`` drops the last document and leaves a ranking that looks
    perfectly valid, so the corpus quietly shrinks and every metric measured on
    it reads as a real result.
    """
    if top_k < 0:
        raise ValueError(f"top_k must not be negative, got {top_k}")


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

    Ties are broken by document id, not by the order the corpus happened to be
    in. Arrival order made the ranking — and therefore every metric computed on
    it — depend on how the caller sorted its input: two runs of the same
    comparison could differ in the third decimal, and the difference would read
    as a finding. ``sort`` is stable, so this was deterministic only as long as
    the input was, and the input is a dict, a set, or a CSV read.

    Args:
        corpus: Documents to rank.
        queries: Query id -> query text.
        scorer: ``scorer(document, query_text) -> float``, higher is better.
        doc_id: ``doc_id(document) -> str``, matching the qrels ids.
        top_k: Keep only the top ``top_k`` documents per query.

    Returns:
        Query id -> ranked document ids.
    """
    _require_non_negative(top_k)

    rankings: Dict[str, List[str]] = {}
    for query_id, text in queries.items():
        scored = [(scorer(doc, text), doc_id(doc)) for doc in corpus]
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        rankings[query_id] = [d for _, d in scored[:top_k]]
    return rankings


def unjudged_in_pool(qrels: Qrels, pool: Sequence[str]) -> set:
    """Pooled documents that carry no judgment in the qrels.

    Useful when building the collection: a pool much larger than the judged set
    means most retrieved documents will be unjudged.
    """
    return set(pool) - pooled_documents(qrels)


@dataclass
class Timing:
    """Wall-clock cost of producing a ranking.

    Reported alongside the metrics because a quality gain that costs two orders
    of magnitude more is not a gain in the same sense. The absence of
    comparative performance figures is a gap the project has named in its own
    positioning, and this is the measurable half of it.
    """

    per_query: Dict[str, float] = field(default_factory=dict)
    pool_size: Dict[str, int] = field(default_factory=dict)

    @property
    def total_seconds(self) -> float:
        return sum(self.per_query.values())

    @property
    def total_documents(self) -> int:
        """Documents scored across all queries — a (query, document) pair count."""
        return sum(self.pool_size.values())

    @property
    def seconds_per_document(self) -> float:
        """Cost per scored pair — the figure that generalises across corpora.

        Total seconds alone would flatter a strategy that was simply given
        fewer documents; this is the per-unit cost.
        """
        total = self.total_documents
        return self.total_seconds / total if total else 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "total_seconds": round(self.total_seconds, 4),
            "total_documents": self.total_documents,
            "seconds_per_document": round(self.seconds_per_document, 8),
            "per_query": {k: round(v, 4) for k, v in sorted(self.per_query.items())},
        }


def build_rankings_timed(
    corpus: Sequence[Any],
    queries: Mapping[str, str],
    scorer: Callable[[Any, str], float],
    doc_id: Callable[[Any], str],
    top_k: int = 100,
) -> Tuple[Dict[str, List[str]], Timing]:
    """``build_rankings`` plus the wall-clock cost of each query.

    The timer wraps only the scoring loop, so it measures the retriever and not
    the harness around it. Ties break the same way they do in ``build_rankings``
    — by document id — so the two cannot disagree about a ranking.
    """
    _require_non_negative(top_k)

    rankings: Dict[str, List[str]] = {}
    timing = Timing()

    for query_id, text in queries.items():
        started = time.perf_counter()
        scored = [(scorer(doc, text), doc_id(doc)) for doc in corpus]
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        timing.per_query[query_id] = time.perf_counter() - started
        timing.pool_size[query_id] = len(corpus)
        rankings[query_id] = [d for _, d in scored[:top_k]]

    return rankings, timing
