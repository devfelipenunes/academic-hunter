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

#: Fallback for the reported score's precision when the caller does not say.
#: The pipeline passes ``settings.score_precision``; the two must agree, because
#: :func:`rerank_scores` builds its lattice *at* the precision the score is
#: written with — a finer lattice would be rounded away and the order lost.
SCORE_DECIMALS = 1

#: Top of the reported score scale.
MAX_SCORE = 10.0

#: How many of the ranking's head documents the cross-encoder reorders. Chosen
#: by measurement: on the judged collection this captures 97% of the ceiling
#: that reranking the whole pool reaches. See `papers/experiments/rerank_eval.py`.
DEFAULT_TOP_N = 20


def rerank_scores(
    base_scores: Sequence[float],
    ranked_indexes: Sequence[int],
    decimals: int = SCORE_DECIMALS,
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
    score is representable at the caller's rounding precision. ``decimals`` must
    match that rounding: a lattice finer than the written value is rounded away
    and takes the order with it.

    The lattice re-spaces the band, so the *count* of candidates above any
    threshold inside it can change. With ``decimals=1`` the reported scale has
    101 levels, and any reordering that is not a tie-break has to spend levels.
    That is why counts like ``included_final`` are not comparable between runs
    with and without the rerank.

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
    ceiling = int(round(MAX_SCORE * unit))

    def on_lattice(value: float) -> int:
        """The score as a whole number of lattice steps, clamped to the scale."""
        return min(max(int(round(round(value, decimals) * unit)), 0), ceiling)

    # Deduplicate while preserving order: a caller that repeats an index would
    # otherwise assign it twice and lose the first (better) position.
    candidates = list(dict.fromkeys(ranked_indexes))
    if len(candidates) < 2:
        return out

    # Pruning drops from the bottom of the *base* order, so that order decides
    # who survives a band too narrow to hold everyone. Only the tail is dropped,
    # and each pass drops one, so the loop is bounded by the candidate count.
    by_base = sorted(candidates, key=lambda i: (-out[i], i))
    hi = on_lattice(out[by_base[0]])
    k = len(by_base)
    while k >= 2 and hi - on_lattice(out[by_base[k - 1]]) + 1 < k:
        k -= 1
    if k < 2:
        # Nothing to reorder, or no lattice wide enough to hold the candidates.
        return out

    kept = set(by_base[:k])
    span = hi - on_lattice(out[by_base[k - 1]])
    positions: List[int] = []
    for j, index in enumerate(i for i in candidates if i in kept):
        position = int(round(hi - j * span / (k - 1)))
        if positions and position >= positions[-1]:
            # Rounding can collide two neighbours; force descent so the exported
            # order is exactly the cross-encoder's order.
            position = positions[-1] - 1
        positions.append(position)
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
    if not texts:
        # Checked before the load: loading the model costs ~6 s to discover, and
        # there would be nothing to score anyway.
        return []

    model = get_cross_encoder(model_name, max_length=max_length)
    if model is None:
        return None

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
        # `is True` on purpose. `bool("false")` is `True`, so a stringly-typed
        # `"enabled": "false"` would silently switch on a ~6 s model load — the
        # opposite of what this function promises for an unusable value. Only a
        # real boolean enables it; anything else leaves it off.
        "enabled": cfg.get("enabled", False) is True,
        "model": str(cfg.get("model", DEFAULT_CE_MODEL)),
        "top_n": _positive_int(cfg.get("top_n"), DEFAULT_TOP_N),
        "max_length": _positive_int(cfg.get("max_length"), DEFAULT_CE_MAX_LENGTH),
    }
