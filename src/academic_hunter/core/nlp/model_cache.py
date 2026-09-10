"""Cached factories for the `sentence-transformers` models the tools load.

Lazy and keyed by model name, so a process loads each one once. The import sits
inside the loader because the package is the optional ``ml`` extra and ``core/``
must not pull it in at import time. Nothing here raises: an unavailable model
returns ``None`` so callers keep their degraded path.
"""

import logging
import threading
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger("academic_hunter.model_cache")

_ST_CACHE: Dict[str, Any] = {}

#: ``max_length`` is part of the key — same weights, different truncation, two
#: different models.
_CE_CACHE: Dict[Tuple[str, int], Any] = {}

#: Guards both caches. See `_load_cached` for what it does and does not cover.
_LOCK = threading.Lock()

DEFAULT_ST_MODEL = "all-MiniLM-L6-v2"
DEFAULT_CE_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
DEFAULT_CE_MAX_LENGTH = 512


def _load_cached(
    cache: Dict[Any, Any],
    key: Any,
    label: str,
    load: Callable[[], Any],
) -> Optional[Any]:
    """The cached model for ``key``, built once by ``load``.

    The load runs outside the lock: two threads racing on an unseen model build
    two copies, which costs seconds once, while holding the lock across a
    multi-second load would block every other tool for its duration.

    Failures are not remembered, so a server started before the extra was
    installed picks it up on the next call instead of needing a restart.
    """
    with _LOCK:
        if key in cache:
            return cache[key]

    try:
        model = load()
    except ImportError as e:
        logger.info("sentence-transformers not installed (%s); %s unavailable.", e, label)
        return None
    except Exception as e:  # noqa: BLE001 — a broken load must not kill the caller
        logger.warning("Failed to load %s: %s", label, e)
        return None

    with _LOCK:
        cache[key] = model
    return model


def get_sentence_transformer(model_name: str = DEFAULT_ST_MODEL) -> Optional[Any]:
    """Return a cached ``SentenceTransformer``, or ``None`` if unavailable.

    The instance is shared — do not mutate its configuration.
    """
    def load() -> Any:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(model_name)
        logger.info("Loaded SentenceTransformer %s.", model_name)
        return model

    return _load_cached(_ST_CACHE, model_name, model_name, load)


def get_cross_encoder(
    model_name: str = DEFAULT_CE_MODEL,
    max_length: int = DEFAULT_CE_MAX_LENGTH,
) -> Optional[Any]:
    """Return a cached ``CrossEncoder``, or ``None`` if unavailable.

    A different ``max_length`` gets its own entry rather than reconfiguring a
    shared one: the model truncates, and a shorter window silently drops the tail
    of a long abstract.
    """
    def load() -> Any:
        from sentence_transformers import CrossEncoder

        model = CrossEncoder(model_name, max_length=max_length)
        logger.info("Loaded CrossEncoder %s (max_length=%d).", model_name, max_length)
        return model

    label = f"{model_name} (max_length={max_length})"
    return _load_cached(_CE_CACHE, (model_name, max_length), label, load)


def clear_model_cache() -> None:
    """Drop every cached model.

    For tests: without it a mock installed by one test would satisfy the next,
    which would pass without exercising anything.
    """
    with _LOCK:
        _ST_CACHE.clear()
        _CE_CACHE.clear()
