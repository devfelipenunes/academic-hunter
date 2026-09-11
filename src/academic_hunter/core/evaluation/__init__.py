"""Retrieval evaluation — metrics and a small judged collection.

The pipeline had no way to tell whether a retrieval change helped: scores were
compared against each other, but nothing measured retrieval quality against
human judgments. Without that, "the new embedding is better" is unfalsifiable.

This package supplies the missing criterion:

- ``metrics`` — nDCG@k, recall@k, precision@k, MRR and MAP over graded qrels.
- ``qrels`` — the judged-collection format, its loader and its validator.
- ``runner`` — score a ranked list (or a callable retriever) against the qrels.

Everything here is pure: no network, no model, no LLM.
"""

from .metrics import (
    average_precision,
    dcg_at_k,
    evaluate_ranking,
    mean_metrics,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from .qrels import (
    Judgment,
    Qrels,
    QrelsError,
    doc_id_for,
    documents_for,
    load_qrels,
    topics,
)
from .runner import (
    EvaluationReport,
    Ranking,
    Timing,
    build_rankings,
    build_rankings_timed,
    evaluate_run,
    unjudged_in_pool,
)

__all__ = [
    # metrics
    "dcg_at_k",
    "ndcg_at_k",
    "recall_at_k",
    "precision_at_k",
    "reciprocal_rank",
    "average_precision",
    "evaluate_ranking",
    "mean_metrics",
    # qrels
    "Judgment",
    "Qrels",
    "QrelsError",
    "load_qrels",
    "doc_id_for",
    "documents_for",
    "topics",
    # runner
    "Ranking",
    "EvaluationReport",
    "evaluate_run",
    "build_rankings",
    "build_rankings_timed",
    "Timing",
    "unjudged_in_pool",
]
