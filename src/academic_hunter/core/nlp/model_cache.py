"""Cached factories for the ML models the interface layer loads.

Every call site used to build its own model. Loading
``cross-encoder/ms-marco-MiniLM-L-6-v2`` was measured at **5.9 s** on CPU, and
the seven call sites in ``interfaces/mcp/tools/`` (six ``SentenceTransformer``,
one ``CrossEncoder``) paid it again on every single invocation — the model
handle is the expensive part, and nothing kept it.

The factories here are lazy and keyed by model name, so a process loads each
model once. ``sentence-transformers`` is imported *inside* the function rather
than at module level for two reasons: it lives in the optional ``ml`` extra, and
``core/`` must not pull a heavy ML dependency at import time — the architecture
test in ``tests/test_architecture.py`` pins the layer boundaries, and the
screener's ``embedding_function`` property set the precedent for a guarded,
lazy import with a fallback.

Nothing here raises. A missing or broken dependency returns ``None`` so callers
keep their existing degraded path (bi-encoder results, or the tool's own
"not installed" message).
"""

import logging
import threading
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("academic_hunter.model_cache")

#: SentenceTransformer name -> loaded model (or None if it failed to load).
_ST_CACHE: Dict[str, Any] = {}

#: (name, max_length) -> loaded model. ``max_length`` is part of the key: two
#: call sites asking for the same weights with a different truncation are two
#: different models.
_CE_CACHE: Dict[Tuple[str, int], Any] = {}

#: Guards both caches. Held only while a dictionary is read or written — the
#: load itself runs outside it. Two threads racing on the same unseen model
#: would load it twice, which wastes a few seconds once; holding the lock across
#: a multi-second load would instead block every other tool for its duration.
#: Same trade-off, and the same reasoning, as `SemanticScreener._embed_paper`.
_LOCK = threading.Lock()

DEFAULT_ST_MODEL = "all-MiniLM-L6-v2"
DEFAULT_CE_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
DEFAULT_CE_MAX_LENGTH = 512


def get_sentence_transformer(model_name: str = DEFAULT_ST_MODEL) -> Optional[Any]:
    """Return a cached ``SentenceTransformer``, or ``None`` if unavailable.

    The returned object is shared: callers must not mutate its configuration,
    since another call site may be holding the same instance.
    """
    with _LOCK:
        if model_name in _ST_CACHE:
            return _ST_CACHE[model_name]

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        logger.info("sentence-transformers not installed (%s); %s unavailable.", e, model_name)
        model = None
    else:
        try:
            model = SentenceTransformer(model_name)
            logger.info("Loaded SentenceTransformer %s.", model_name)
        except Exception as e:  # noqa: BLE001 — a broken load must not kill the caller
            logger.warning("Failed to load SentenceTransformer %s: %s", model_name, e)
            model = None

    if model is not None:
        # Failures are deliberately not cached: `sentence-transformers` is an
        # optional extra, and a server that started before it was installed
        # should pick it up on the next call rather than need a restart.
        with _LOCK:
            _ST_CACHE[model_name] = model
    return model


def get_cross_encoder(
    model_name: str = DEFAULT_CE_MODEL,
    max_length: int = DEFAULT_CE_MAX_LENGTH,
) -> Optional[Any]:
    """Return a cached ``CrossEncoder``, or ``None`` if unavailable.

    ``max_length`` matters: the ms-marco model truncates, and a shorter window
    silently drops the tail of a long abstract. Callers that need a different
    truncation get their own entry rather than reconfiguring a shared one.
    """
    key = (model_name, max_length)
    with _LOCK:
        if key in _CE_CACHE:
            return _CE_CACHE[key]

    try:
        from sentence_transformers import CrossEncoder
    except ImportError as e:
        logger.info("sentence-transformers not installed (%s); %s unavailable.", e, model_name)
        model = None
    else:
        try:
            model = CrossEncoder(model_name, max_length=max_length)
            logger.info("Loaded CrossEncoder %s (max_length=%d).", model_name, max_length)
        except Exception as e:  # noqa: BLE001 — a broken load must not kill the caller
            logger.warning("Failed to load CrossEncoder %s: %s", model_name, e)
            model = None

    if model is not None:
        # See `get_sentence_transformer`: a failure is retried, not remembered.
        with _LOCK:
            _CE_CACHE[key] = model
    return model


def clear_model_cache() -> None:
    """Drop every cached model.

    For tests: a cached model would otherwise survive between them, hiding a
    load that a test expected to observe — and, worse, letting a mock installed
    by one test satisfy a later one that never asked for it. The MCP suite resets
    its module-level caches the same way (``_clear_mcp_caches`` in
    ``tests/interfaces/mcp/conftest.py``).
    """
    with _LOCK:
        _ST_CACHE.clear()
        _CE_CACHE.clear()
