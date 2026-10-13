"""Fusion of the keyword and embedding signals into the reported score.

Kept as a pure function, separate from the pipeline step that calls it, so that
anything measuring the fused score measures *the code that actually ships*. A
second implementation of the same rule is free to drift from this one, and a
measurement taken against it would silently stop describing what runs.
"""

import math
from typing import Dict, Optional, Sequence

DEFAULT_STRATEGY = "weighted_norm"

IMPLEMENTED_STRATEGIES = ("weighted_norm", "rank_geometric")

DEFAULT_WEIGHTS = {"keyword": 0.7, "embedding": 0.3, "citation": 0.0}


def percentile_ranks(values: Sequence[float]) -> list:
    """Percentile rank of each value in [0, 1], ties resolved by last position.

    Matches what the pipeline has always computed: sort, then assign
    ``position / (n - 1)``.
    """
    n = len(values)
    if n < 2:
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


def resolve_weights(
    weights: Optional[Dict[str, float]] = None,
    cit_scores: Optional[Sequence[float]] = None,
) -> Dict[str, float]:
    """The weights the fusion will actually apply, overrides included.

    ``fuse_scores`` decides three things about the weights it was handed, and
    all three were buried inside it: a missing key falls back to
    ``DEFAULT_WEIGHTS``, a negative weight is read as zero, a citation weight is
    dropped when the counts do not vary, and an all-zero set is replaced by
    keyword alone. Reading them off the config therefore described a different
    run from the one that happened.

    Named and returned instead, so the run can record what it did. Nothing here
    chooses a weight: the caller's values are returned, or the defaults it did
    not override. Choosing is a judgement about the corpus, and it needs judged
    papers to argue from.
    """
    merged = {**DEFAULT_WEIGHTS, **(weights or {})}
    alpha = max(0.0, float(merged["keyword"]))
    beta = max(0.0, float(merged["embedding"]))
    gamma = max(0.0, float(merged.get("citation", 0.0)))
    if not cit_scores or max(cit_scores) == min(cit_scores):
        gamma = 0.0
    if alpha + beta + gamma <= 0:
        alpha, beta, gamma = 1.0, 0.0, 0.0
    return {"keyword": alpha, "embedding": beta, "citation": gamma}


def fuse_scores(
    kw_scores: Sequence[float],
    sem_scores: Sequence[float],
    strategy: str = DEFAULT_STRATEGY,
    weights: Optional[Dict[str, float]] = None,
    cit_scores: Optional[Sequence[float]] = None,
) -> list:
    """Combine the keyword, embedding and citation signals into a 0-10 score.

    ``weighted_norm`` (the default) min-max normalises each signal and takes a
    weighted sum, so a paper strong on one signal is not dragged down by being
    mid-pack on the other.

    ``rank_geometric`` is the superseded rule, ``sqrt(rank_kw * rank_sem) * 10``,
    kept so earlier runs stay reproducible. It measured worse than either of its
    own inputs on a hand-judged sample: flattening both signals to percentile
    ranks before combining discards magnitude. It takes the two signals it was
    defined on and ignores citations; a third term would stop it reproducing the
    runs it exists to reproduce.

    When every fused value is identical *because the inputs were*, there is
    nothing to rank, and the papers tie at the top of the scale. They must not
    tie at the bottom: a zero reads as "irrelevant" at the threshold filter,
    which would silently empty the run — the same failure mode as a single-paper
    collection. Identical fused values with varying inputs are a different
    situation, and are scored as what they are; see ``_nothing_to_rank``.

    ``rank_geometric`` reads the same guard, on the two signals it was defined
    on. Without it, a flat input went through ``percentile_ranks``, which breaks
    ties by insertion order, and ``sqrt(a*b)*10`` turned that into a ladder from
    0 to 10 — so the paper that arrived last scored highest and passed the
    threshold, on no evidence at all.

    Args:
        kw_scores: Raw keyword scores, one per paper.
        sem_scores: Raw embedding scores, one per paper.
        strategy: ``weighted_norm`` or ``rank_geometric`` — see
            ``IMPLEMENTED_STRATEGIES``. Any other string, including one that
            names a rule that was measured and never shipped, falls through to
            ``weighted_norm`` without saying so, which is why the list is
            exported: a caller that compares rules has to be able to ask which
            ones exist instead of reading them off a table.
        weights: ``{"keyword": α, "embedding": β, "citation": γ}``; defaults to
            0.7/0.3/0.0. Negative weights are read as zero. A weight is a
            proportion, so a negative one has no meaning, and leaving it in let
            the sum escape the [0, 10] this function promises: a keyword weight
            of -1 against an embedding weight of 2 has a positive total, passes
            the zero-sum guard, and scores the two extremes of the collection at
            -10 and +20. The citation weight defaults to zero, so passing
            ``cit_scores`` alone changes nothing: the list is data, the weight is
            the decision to use it. A citation weight on a corpus whose counts do
            not vary is read as zero as well, because ``_minmax`` flattens a
            constant to zeros and a weight that takes its share of the total
            without contributing a value would rescale every score — the ranking
            would survive, the reported number would not. The keyword and
            embedding weights keep their historical behaviour here, because
            changing it would move runs this function exists to reproduce.
        cit_scores: Raw citation magnitudes, one per paper. ``None`` means the
            caller has no citation signal, which is not the same as every paper
            scoring zero.

    Returns:
        Final scores in [0, 10], aligned with the input order.

    Raises:
        ValueError: If the sequences differ in length.
    """
    if len(kw_scores) != len(sem_scores):
        raise ValueError(
            f"kw_scores and sem_scores must align: {len(kw_scores)} vs {len(sem_scores)}"
        )
    if cit_scores is not None and len(cit_scores) != len(kw_scores):
        raise ValueError(
            f"cit_scores must align with the others: {len(cit_scores)} vs {len(kw_scores)}"
        )
    n = len(kw_scores)
    if n == 0:
        return []

    if strategy == "rank_geometric":
        if _nothing_to_rank(kw_scores, sem_scores, 1.0, 1.0):
            evidence = any(kw_scores) or any(sem_scores)
            return [10.0] * n if evidence else [0.0] * n
        rank_kw = percentile_ranks(kw_scores)
        rank_sem = percentile_ranks(sem_scores)
        return [math.sqrt(a * b) * 10.0 for a, b in zip(rank_kw, rank_sem)]

    effective = resolve_weights(weights, cit_scores)
    alpha = effective["keyword"]
    beta = effective["embedding"]
    gamma = effective["citation"]
    total = alpha + beta + gamma

    kw_norm = _minmax(kw_scores)
    sem_norm = _minmax(sem_scores)
    cit_norm = _minmax(cit_scores) if gamma > 0 else [0.0] * n
    fused = [
        (alpha * a + beta * b + gamma * c) / total
        for a, b, c in zip(kw_norm, sem_norm, cit_norm)
    ]

    if max(fused) == min(fused):
        if _nothing_to_rank(kw_scores, sem_scores, alpha, beta, cit_scores, gamma):
            evidence = (
                (alpha > 0 and any(kw_scores))
                or (beta > 0 and any(sem_scores))
                or (gamma > 0 and cit_scores is not None and any(cit_scores))
            )
            return [10.0] * n if evidence else [0.0] * n
        return [fused[0] * 10.0] * n

    return [f * 10.0 for f in fused]


def _nothing_to_rank(
    kw_scores: Sequence[float],
    sem_scores: Sequence[float],
    alpha: float,
    beta: float,
    cit_scores: Optional[Sequence[float]] = None,
    gamma: float = 0.0,
) -> bool:
    """Whether every signal that carries weight is itself flat.

    A flat fused score has two causes and they call for opposite answers. If the
    inputs are flat then normalising them — which maps a constant to zeros —
    destroyed the ordering, and the papers tie at the top of the scale. If the
    inputs vary but the fused value is still constant, the weighting made them
    cancel: keyword-strong and embedding-strong papers are not equal, they are
    opposite, and the honest score is the fused value itself (0.5 → 5.0), not the
    top of the scale.

    Reading the second case as the first approved the whole corpus: four papers
    on opposite signals came out at 10.0 each and sailed past the threshold.

    A signal weighted zero cannot contribute a value, so its flatness is not
    evidence of anything and does not enter into it. A whole corpus at zero
    citations is the case that matters: the counts do not vary, so they carry no
    ordering, and the pair decides exactly as it did before citations existed.
    """
    keyword_flat = alpha == 0 or max(kw_scores) == min(kw_scores)
    embedding_flat = beta == 0 or max(sem_scores) == min(sem_scores)
    citation_flat = (
        gamma == 0
        or cit_scores is None
        or max(cit_scores) == min(cit_scores)
    )
    return keyword_flat and embedding_flat and citation_flat
