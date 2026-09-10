"""Cached factories for the ML models the interface layer loads.

Every call site used to build its own model. Loading
``cross-encoder/ms-marco-MiniLM-L-6-v2`` was measured at **5.9 s** on CPU, and
the seven call sites in ``interfaces/mcp/tools/`` (six ``SentenceTransformer``,
one ``CrossEncoder``) paid it again on every single invocation — the model
handle is the expensive part, and nothing kept it.

The factories here are lazy and keyed by model name, so a process loads each
``sentence-transformers`` model once. ChromaDB's ``DefaultEmbeddingFunction``
and ``BERTopic`` are deliberately out of scope: the first is loaded by an ONNX
session an order of magnitude cheaper than a torch checkpoint, and the second is
a fitted estimator that mutates on every ``fit_transform``.

``sentence-transformers`` is imported *inside* the loader rather than at module
level for two reasons: it lives in the optional ``ml`` extra, and ``core/`` must
not pull a heavy ML dependency at import time — the architecture test in
``tests/test_architecture.py`` pins the layer boundaries, and the screener's
``embedding_function`` property set the precedent for a guarded, lazy import
with a fallback.

Nothing here raises. A missing or broken dependency returns ``None`` so callers
keep their existing degraded path (bi-encoder results, or the tool's own
"not installed" message).
"""

import logging
import threading
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger("academic_hunter.model_cache")

#: SentenceTransformer name -> loaded model.
_ST_CACHE: Dict[str, Any] = {}

#: (name, max_length) -> loaded model. ``max_length`` is part of the key: two
#: call sites asking for the same weights with a different truncation are two
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

    Held under no lock while loading: two threads racing on the same unseen
    model would build two copies, which wastes a few seconds once — whereas
    holding the lock across a multi-second load would block every other tool for
    its duration. Same trade-off, and the same reasoning, as
    ``SemanticScreener._embed_paper``.

    A failure is not remembered. ``sentence-transformers`` is an optional extra,
    and a server that started before it was installed should pick it up on the
    next call rather than need a restart.
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

    The returned object is shared: callers must not mutate its configuration,
    since another call site may be holding the same instance.
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

    ``max_length`` matters: the ms-marco model truncates, and a shorter window
    silently drops the tail of a long abstract. Callers that need a different
    truncation get their own entry rather than reconfiguring a shared one.
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

    For tests: a cached model would otherwise survive between them, hiding a
    load that a test expected to observe — and, worse, letting a mock installed
    by one test satisfy a later one that never asked for it. The MCP suite resets
    its module-level caches the same way (``_clear_mcp_caches`` in
    ``tests/interfaces/mcp/conftest.py``).
    """
    with _LOCK:
        _ST_CACHE.clear()
        _CE_CACHE.clear()
