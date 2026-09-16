"""Second-stage reranking with a cross-encoder.

Scores ``(query, document)`` as a pair, which neither first-stage signal does,
and reorders only the head of a ranking — it is far too slow for a corpus.
"""

import logging
from typing import Any, Dict, List, Optional, Sequence

from ..infra.config import positive_int
from .model_cache import DEFAULT_CE_MAX_LENGTH, DEFAULT_CE_MODEL, get_cross_encoder

logger = logging.getLogger("academic_hunter.reranker")

#: Fallback precision for the reported score. Must match the rounding the
#: pipeline writes with — see :func:`rerank_scores`.
SCORE_DECIMALS = 1

MAX_SCORE = 10.0

#: Head size. Measured: captures 97% of the ceiling the whole pool reaches.
DEFAULT_TOP_N = 20


def rerank_scores(
    base_scores: Sequence[float],
    ranked_indexes: Sequence[int],
    decimals: int = SCORE_DECIMALS,
) -> List[float]:
    """Redistribute the candidates' own scores along the reranked order.

    ``ranked_indexes`` are positions into ``base_scores``, best first. Scores
    outside them are left alone. The ``k`` candidates take the ``k`` values of a
    lattice stepping by ``10**-decimals`` from their own maximum to their own
    minimum, so the extremes survive exactly and nothing leaves the band its own
    members defined.

    The lattice is the point: the obvious rule — hand the candidates' existing
    scores back in the new order — preserves the multiset and still loses, because
    ``Relevance_Score`` is rounded to one decimal and everything downstream sorts
    on the rounded value. Two scores of 7.24 and 7.21 both become 7.2, and the
    sort falls back to insertion order. ``decimals`` must match that rounding: a
    finer lattice is rounded away and takes the order with it.

    A band too narrow to hold ``k`` distinct values drops its lowest-scoring
    candidate and retries; it is never widened, which would push papers past the
    floor their peers defined.
    """
    out = [float(s) for s in base_scores]
    unit = 10 ** decimals
    ceiling = int(round(MAX_SCORE * unit))

    def on_lattice(value: float) -> int:
        return min(max(int(round(round(value, decimals) * unit)), 0), ceiling)

    candidates = list(dict.fromkeys(ranked_indexes))
    if len(candidates) < 2:
        return out

    # Pruning drops from the bottom of the base order, so that order decides who
    # survives a narrow band. One per pass, so the loop is bounded.
    by_base = sorted(candidates, key=lambda i: (-out[i], i))
    hi = on_lattice(out[by_base[0]])
    k = len(by_base)
    while k >= 2 and hi - on_lattice(out[by_base[k - 1]]) + 1 < k:
        k -= 1
    if k < 2:
        return out

    kept = set(by_base[:k])
    span = hi - on_lattice(out[by_base[k - 1]])
    positions: List[int] = []
    for j, index in enumerate(i for i in candidates if i in kept):
        position = int(round(hi - j * span / (k - 1)))
        if positions and position >= positions[-1]:
            # Rounding can collide two neighbours; the exported order has to be
            # exactly the cross-encoder's.
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

    ``None`` is distinct from a raised exception: the caller has to tell "not
    installed" from "it broke", and neither may fail a run.
    """
    if not texts:
        return []

    model = get_cross_encoder(model_name, max_length=max_length)
    if model is None:
        return None

    scores = model.predict([[query, text] for text in texts])
    return [float(s) for s in scores]


def rerank_config(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise ``settings.rerank``, which has no schema and may hold anything."""
    raw = settings.get("rerank")
    cfg = raw if isinstance(raw, dict) else {}

    return {
        # `is True`, not truthiness: `bool("false")` is True, so `"enabled":
        # "false"` would switch on a ~6 s model load.
        "enabled": cfg.get("enabled", False) is True,
        "model": str(cfg.get("model", DEFAULT_CE_MODEL)),
        "top_n": positive_int(cfg.get("top_n"), DEFAULT_TOP_N),
        "max_length": positive_int(cfg.get("max_length"), DEFAULT_CE_MAX_LENGTH),
    }
