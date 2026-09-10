"""Ranking metrics over a judged collection.

Conventions, stated once because they are easy to get subtly wrong:

- A **ranking** is a list of document ids, most relevant first, as the retriever
  produced it.
- **Relevance grades** are integers; ``0`` means judged not relevant, ``>= 1``
  means relevant, and higher means more relevant. A document absent from the
  judgments is treated as ``0`` — unjudged is not the same as *relevant*, and
  the standard pooled-evaluation assumption is to score it as not relevant.
- ``k`` is a rank position (1-based), so ``ndcg_at_k(ids, rel, 10)`` looks at
  the first ten documents.

Gains use the exponential form ``2^grade - 1``, which is the standard for graded
relevance (it rewards putting a grade-3 document above three grade-1 documents).
``linear_gain=True`` switches to the raw grade, useful when the grades are
ordinal rather than additive.
"""

import math
from typing import Any, Dict, Iterable, Mapping, Sequence

#: Default rank cutoffs reported by :func:`evaluate_ranking`.
DEFAULT_KS: tuple[int, ...] = (5, 10, 20)


def _gain(grade: int, linear_gain: bool = False) -> float:
    """Convert a relevance grade into its gain contribution."""
    if linear_gain:
        return float(grade)
    return float((2 ** grade) - 1)


def dcg_at_k(
    ranking: Sequence[Any],
    relevance: Mapping[Any, int],
    k: int,
    linear_gain: bool = False,
) -> float:
    """Discounted cumulative gain over the first ``k`` positions.

    Uses the ``log2(rank + 1)`` discount, so position 1 is undiscounted and
    position 2 is halved.
    """
    if k <= 0:
        return 0.0

    total = 0.0
    for rank, doc_id in enumerate(ranking[:k], start=1):
        grade = relevance.get(doc_id, 0)
        if grade <= 0:
            continue
        total += _gain(grade, linear_gain) / math.log2(rank + 1)
    return total


def ndcg_at_k(
    ranking: Sequence[Any],
    relevance: Mapping[Any, int],
    k: int,
    linear_gain: bool = False,
) -> float:
    """Normalised DCG: DCG divided by the best achievable DCG for this query.

    Returns ``0.0`` when the query has no relevant documents at all — there is
    no ideal ranking to normalise against, and inventing one would report a
    score for a query that cannot be answered.
    """
    if k <= 0:
        return 0.0

    ideal_grades = sorted(
        (g for g in relevance.values() if g > 0), reverse=True
    )[:k]
    if not ideal_grades:
        return 0.0

    ideal = sum(
        _gain(g, linear_gain) / math.log2(rank + 1)
        for rank, g in enumerate(ideal_grades, start=1)
    )
    if ideal == 0.0:
        return 0.0

    return dcg_at_k(ranking, relevance, k, linear_gain) / ideal


def recall_at_k(
    ranking: Sequence[Any],
    relevance: Mapping[Any, int],
    k: int,
    threshold: int = 1,
) -> float:
    """Fraction of the judged-relevant documents that appear in the top ``k``.

    ``threshold`` is the minimum grade counted as relevant. A query with no
    relevant documents has no recall to measure and returns ``0.0``.
    """
    relevant = {d for d, g in relevance.items() if g >= threshold}
    if not relevant:
        return 0.0
    if k <= 0:
        return 0.0

    retrieved = set(ranking[:k]) & relevant
    return len(retrieved) / len(relevant)


def precision_at_k(
    ranking: Sequence[Any],
    relevance: Mapping[Any, int],
    k: int,
    threshold: int = 1,
) -> float:
    """Fraction of the top ``k`` positions that are relevant.

    Divides by ``k``, not by the number of documents actually returned: a
    retriever that returns three documents when ten were asked for should not
    be credited with perfect precision.
    """
    if k <= 0:
        return 0.0

    top = ranking[:k]
    hits = sum(1 for d in top if relevance.get(d, 0) >= threshold)
    return hits / k


def reciprocal_rank(
    ranking: Sequence[Any], relevance: Mapping[Any, int], threshold: int = 1
) -> float:
    """Inverse of the rank of the first relevant document (``0.0`` if none)."""
    for rank, doc_id in enumerate(ranking, start=1):
        if relevance.get(doc_id, 0) >= threshold:
            return 1.0 / rank
    return 0.0


def average_precision(
    ranking: Sequence[Any], relevance: Mapping[Any, int], threshold: int = 1
) -> float:
    """Mean of the precision values at each relevant position.

    Normalised by the total number of judged-relevant documents, so a retriever
    that finds only the easy half of them is penalised.
    """
    relevant = {d for d, g in relevance.items() if g >= threshold}
    if not relevant:
        return 0.0

    hits = 0
    total = 0.0
    for rank, doc_id in enumerate(ranking, start=1):
        if doc_id in relevant:
            hits += 1
            total += hits / rank

    return total / len(relevant)


def evaluate_ranking(
    ranking: Sequence[Any],
    relevance: Mapping[Any, int],
    ks: Iterable[int] = DEFAULT_KS,
    linear_gain: bool = False,
    threshold: int = 1,
) -> Dict[str, float]:
    """Compute the full metric set for one query's ranking.

    Returns a flat dict keyed like ``ndcg@10`` / ``recall@5``, plus ``mrr`` and
    ``ap`` which are rank-independent.
    """
    ks = sorted({int(k) for k in ks if int(k) > 0})
    out: Dict[str, float] = {}

    for k in ks:
        out[f"ndcg@{k}"] = ndcg_at_k(ranking, relevance, k, linear_gain)
        out[f"recall@{k}"] = recall_at_k(ranking, relevance, k, threshold)
        out[f"precision@{k}"] = precision_at_k(ranking, relevance, k, threshold)

    out["mrr"] = reciprocal_rank(ranking, relevance, threshold)
    out["ap"] = average_precision(ranking, relevance, threshold)
    return out


def mean_metrics(per_query: Sequence[Mapping[str, float]]) -> Dict[str, float]:
    """Average a list of metric dicts key by key.

    Returns an empty dict for an empty input rather than raising: a run with no
    judged queries has no mean, and callers report that as "n/a".
    """
    if not per_query:
        return {}

    keys = set(per_query[0])
    for m in per_query[1:]:
        keys &= set(m)

    return {k: sum(m[k] for m in per_query) / len(per_query) for k in sorted(keys)}
