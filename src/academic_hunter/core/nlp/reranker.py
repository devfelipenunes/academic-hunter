"""Second-stage reranking with a cross-encoder.

The pipeline's fused score comes from two signals that never see the *question*
as a pair: BM25 matches terms, the embedding compares a paper against a domain
centroid. A cross-encoder reads ``(query, document)`` together and is the
standard second stage in retrieval — it is far too slow to rank a corpus, but
affordable over the head of a ranking.

Measured on the judged collection (108 documents, 11 queries, nDCG@10), with
BM25 as the first stage:

===============  ========  =========  =========
strategy         nDCG@5    nDCG@10    nDCG@20
===============  ========  =========  =========
bm25 (baseline)  0.6459    0.6728     0.7394
+ rerank top-20  0.8007    0.7668     0.7964
+ rerank top-30  0.7967    0.7802     0.8413
ce_oracle        0.8114    0.7916     0.8512
===============  ========  =========  =========

It wins on both topics separately (blockchain_governance +0.1544,
genre_analysis +0.0436) and top-20 captures 97% of the oracle ceiling. That
contrasts with the bi-encoder embedding, which *lowers* nDCG monotonically as
its weight grows — the two are not interchangeable and the difference is only
visible by measuring.

Cost on CPU: ~214 ms per pair at ``max_length=512`` over real abstracts, and
~5.9 s to load the model. Hence the cache in :mod:`academic_hunter.core.nlp.model_cache`
and hence a small ``top_n``.

This module is deliberately split in two: :func:`rerank_scores` is pure
arithmetic and holds the delicate part (see its docstring), while
:func:`rerank_texts` is the thin wrapper that touches the model.
"""

import logging
from typing import Any, Dict, List, Optional, Sequence

from .model_cache import DEFAULT_CE_MAX_LENGTH, DEFAULT_CE_MODEL, get_cross_encoder

logger = logging.getLogger("academic_hunter.reranker")

#: The pipeline rounds ``Relevance_Score`` to this many decimals. Reranking has
#: to work *at* that precision, not around it — see :func:`rerank_scores`.
SCORE_DECIMALS = 1

#: Top of the reported score scale.
MAX_SCORE = 10.0


def rerank_scores(
    base_scores: Sequence[float],
    ranked_indexes: Sequence[int],
    decimals: int = SCORE_DECIMALS,
    max_score: float = MAX_SCORE,
) -> List[float]:
    """Redistribute the candidates' own scores along the reranked order.

    ``ranked_indexes`` are positions into ``base_scores``, best first, as the
    cross-encoder ordered them. The return value is a new list aligned with
    ``base_scores``; documents outside ``ranked_indexes`` keep their exact score.

    The rule is "the reranker redistributes the band the candidates already
    occupy". Concretely, the ``k`` candidates take the ``k`` values of a lattice
    stepping by ``10**-decimals`` from **their own** maximum down to **their
    own** minimum, in cross-encoder order. The extremes survive exactly and
    nothing leaves the band its own members defined; the interior values are
    nudged onto the lattice, by at most half a step, so that every assigned
    score is representable at the pipeline's rounding precision.

    That last property is the whole point. The obvious rule — hand the
    candidates' existing scores back in the new order — preserves the multiset
    perfectly and is wrong here, because ``RecomputeRanksStep`` rounds
    ``Relevance_Score`` to one decimal and everything downstream sorts on the
    *rounded* value. Two base scores of 7.24 and 7.21 both become 7.2, and the
    stable sort then undoes the reranking by falling back to insertion order.
    Measured on the top-20 of the judged pools, the base ranking already
    produces only 14-19 distinct values once rounded. Building the lattice at
    export precision removes the collision instead of losing to it.

    When the band is too narrow to hold ``k`` distinct values — everything at
    9.9-10.0, say — the lowest-scoring candidate by *base* score is dropped from
    the reranked set and the lattice is recomputed. The band is never widened:
    doing so would push papers past the floor their own peers defined. The loop
    terminates (``k`` drops by one per pass) and degrades correctly: candidates
    that all tie end up reranking nothing and ``base_scores`` is returned
    unchanged, which matches how :func:`~academic_hunter.core.nlp.fusion.fuse_scores`
    treats a flat signal.

    Note the consequence of a bounded band: the reranked set is sorted among
    itself, but a document just outside ``ranked_indexes`` can still outrank the
    weakest reranked one. That is intended — the cross-encoder judged it worse
    than its peers — and it means ``top_n`` is an upper bound on how many
    documents are reordered, not a guarantee about the cut.
    """
    out = [float(s) for s in base_scores]
    unit = 10 ** decimals
    ceiling = int(round(max_score * unit))

    # Deduplicate while preserving order: a caller that repeats an index would
    # otherwise assign it twice and lose the first (better) position.
    candidates = list(dict.fromkeys(ranked_indexes))

    while True:
        k = len(candidates)
        if k < 2:
            # Nothing to reorder, or no room for a distinct-value lattice.
            return out

        by_base = sorted(candidates, key=lambda i: (-out[i], i))
        hi = min(int(round(round(out[by_base[0]], decimals) * unit)), ceiling)
        lo = max(int(round(round(out[by_base[-1]], decimals) * unit)), 0)
        if hi - lo + 1 >= k:
            break
        candidates = [i for i in candidates if i != by_base[-1]]

    span = hi - lo
    positions: List[int] = []
    for j in range(k):
        position = int(round(hi - j * span / (k - 1)))
        if positions and position >= positions[-1]:
            # Rounding can collide two neighbours; force strict descent so the
            # exported order is exactly the cross-encoder's order.
            position = positions[-1] - 1
        positions.append(position)

    for position, index in zip(positions, candidates):
        out[index] = position / unit
    return out


def rerank_texts(
    query: str,
    texts: Sequence[str],
    model_name: str = DEFAULT_CE_MODEL,
    max_length: int = DEFAULT_CE_MAX_LENGTH,
) -> Optional[List[float]]:
    """Score every ``(query, text)`` pair, or ``None`` if the model is missing.

    Returns one score per input text, aligned with ``texts``. ``None`` means the
    cross-encoder is unavailable — a distinct outcome from an exception during
    inference, which propagates so the caller can tell "not installed" from
    "it broke". Callers must treat the failure as non-fatal: this is an optional
    enhancement, and a pipeline that raises because a reranker was missing would
    be worse than one that never had it.
    """
    model = get_cross_encoder(model_name, max_length=max_length)
    if model is None:
        return None
    if not texts:
        return []

    scores = model.predict([[query, text] for text in texts])
    return [float(s) for s in scores]


def rerank_config(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise ``settings.rerank`` into a usable dict.

    The config file has no schema, so every value here is whatever the user
    typed: a string where a number belongs, ``true`` where an object belongs.
    Anything unusable falls back to the default rather than raising — a typo in
    an optional feature must not take down a run.
    """
    raw = settings.get("rerank")
    cfg = raw if isinstance(raw, dict) else {}

    def _positive_int(value: Any, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else default

    return {
        "enabled": bool(cfg.get("enabled", False)),
        "model": str(cfg.get("model", DEFAULT_CE_MODEL)),
        "top_n": _positive_int(cfg.get("top_n"), 20),
        "max_length": _positive_int(cfg.get("max_length"), DEFAULT_CE_MAX_LENGTH),
    }
