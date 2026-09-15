"""Fusion of the keyword and embedding signals into the reported score.

Kept as a pure function, separate from the pipeline step that calls it, so that
the experiment scripts evaluate *the code that actually ships* rather than a
reimplementation of it. A reimplemented fusion in the evaluation would be free
to drift from the real one, and the measurement would silently stop meaning
anything.
"""

import math
from typing import Dict, Optional, Sequence

#: Fusion used when the config does not say otherwise.
DEFAULT_STRATEGY = "weighted_norm"

#: Default signal weights: 70% keyword, 30% embedding.
DEFAULT_WEIGHTS = {"keyword": 0.7, "embedding": 0.3}


def percentile_ranks(values: Sequence[float]) -> list:
    """Percentile rank of each value in [0, 1], ties resolved by last position.

    Matches what the pipeline has always computed: sort, then assign
    ``position / (n - 1)``.
    """
    n = len(values)
    if n < 2:
        # No distribution to rank against; the single value is trivially top.
        return [1.0] * n

    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    for position, index in enumerate(order):
        ranks[index] = position / (n - 1)
    return ranks


def _minmax(values: Sequence[float]) -> list:
    """Min-max normalise to [0, 1]. A constant input maps to all zeros.

    Zeros are the honest answer here: a signal that does not vary carries no
    ordering information, so it should contribute nothing. The caller handles
    the case where *every* signal is flat.
    """
    lo, hi = min(values), max(values)
    if hi - lo == 0:
        return [0.0] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def fuse_scores(
    kw_scores: Sequence[float],
    sem_scores: Sequence[float],
    strategy: str = DEFAULT_STRATEGY,
    weights: Optional[Dict[str, float]] = None,
) -> list:
    """Combine the keyword and embedding signals into a 0-10 score.

    ``weighted_norm`` (the default) min-max normalises each signal and takes a
    weighted sum, so a paper strong on one signal is not dragged down by being
    mid-pack on the other.

    ``rank_geometric`` is the superseded rule, ``sqrt(rank_kw * rank_sem) * 10``,
    kept so earlier runs stay reproducible. It measured worse than either of its
    own inputs on the judged collection: flattening both signals to percentile
    ranks before combining discards magnitude.

    When every fused value is identical there is nothing to rank, and the papers
    tie at the top of the scale. They must not tie at the bottom: a zero reads
    as "irrelevant" at the threshold filter, which would silently empty the run
    — the same failure mode as a single-paper collection.

    Args:
        kw_scores: Raw keyword scores, one per paper.
        sem_scores: Raw embedding scores, one per paper.
        strategy: ``weighted_norm`` or ``rank_geometric``.
        weights: ``{"keyword": α, "embedding": β}``; defaults to 0.7/0.3.

    Returns:
        Final scores in [0, 10], aligned with the input order.

    Raises:
        ValueError: If the two sequences differ in length.
    """
    if len(kw_scores) != len(sem_scores):
        raise ValueError(
            f"kw_scores and sem_scores must align: {len(kw_scores)} vs {len(sem_scores)}"
        )
    n = len(kw_scores)
    if n == 0:
        return []

    if strategy == "rank_geometric":
        rank_kw = percentile_ranks(kw_scores)
        rank_sem = percentile_ranks(sem_scores)
        return [math.sqrt(a * b) * 10.0 for a, b in zip(rank_kw, rank_sem)]

    merged = {**DEFAULT_WEIGHTS, **(weights or {})}
    alpha = float(merged["keyword"])
    beta = float(merged["embedding"])
    total = alpha + beta
    if total <= 0:
        # A zero total would divide by zero, and returning zeros would empty the
        # run at the threshold. Fall back to keyword-only instead.
        alpha, beta, total = 1.0, 0.0, 1.0

    kw_norm = _minmax(kw_scores)
    sem_norm = _minmax(sem_scores)
    fused = [(alpha * a + beta * b) / total for a, b in zip(kw_norm, sem_norm)]

    if max(fused) == min(fused):
        # Every signal is flat, so there is no ordering to preserve. Whether that
        # means "no evidence" or "equal evidence" is what decides the score: an
        # all-zero signal is a query that matched nothing, and tying it at the top
        # of the scale approved the entire corpus at the threshold. `_minmax`
        # already treats a flat signal as contributing nothing — this only asks
        # whether anything was there to contribute.
        evidence = (alpha > 0 and any(kw_scores)) or (beta > 0 and any(sem_scores))
        return [10.0] * n if evidence else [0.0] * n

    return [f * 10.0 for f in fused]
