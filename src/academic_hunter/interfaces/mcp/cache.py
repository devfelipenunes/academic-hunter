"""Simple in-memory cache for MCP tools to avoid repeated API calls.

Uses TTL-based expiration. Thread-safe for async usage.

Three stores live here, and one ordering between two of them is load-bearing.
``discovery_cache`` holds what ``quick_topic_discovery`` replied, and
``discovery_titles`` holds the evidence behind that reply, written by the same
function body. Since ``@cached`` runs the body only on a miss, a call served
from ``discovery_cache`` returns the reply without rewriting the evidence --
so ``discovery_titles`` must not expire first, or the reply is handed back
while the evidence it describes is already gone. Keep its TTL at or above
``discovery_cache``'s.
"""

import inspect
import time
from functools import wraps


class TTLCache:
    """Simple TTL cache with max size."""

    def __init__(self, ttl_seconds: int = 300, max_size: int = 100):
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._store: dict = {}
        self._timestamps: dict = {}

    def get(self, key: str):
        """Get cached value. Returns None if expired or missing."""
        if key not in self._store:
            return None
        if time.time() - self._timestamps[key] > self._ttl:
            del self._store[key]
            del self._timestamps[key]
            return None
        return self._store[key]

    def set(self, key: str, value):
        """Cache a value."""
        if len(self._store) >= self._max_size:
            oldest = min(self._timestamps, key=self._timestamps.get)
            del self._store[oldest]
            del self._timestamps[oldest]
        self._store[key] = value
        self._timestamps[key] = time.time()

    def clear(self):
        """Clear all cached values."""
        self._store.clear()
        self._timestamps.clear()

    def keys(self) -> list:
        """The keys still live, dropping the expired ones on the way out.

        Expiry is otherwise noticed only by a ``get``, so a key nobody asks for
        again stays counted in ``size`` for the life of the process. Enumerating
        is the one operation that has to sweep, or a caller is handed entries no
        ``get`` would ever return.
        """
        now = time.time()
        expired = [
            key for key, stamp in self._timestamps.items()
            if now - stamp > self._ttl
        ]
        for key in expired:
            del self._store[key]
            del self._timestamps[key]
        return list(self._store)

    @property
    def size(self) -> int:
        return len(self._store)


citation_cache = TTLCache(ttl_seconds=600, max_size=200)
discovery_cache = TTLCache(ttl_seconds=300, max_size=100)
discovery_titles = TTLCache(ttl_seconds=3600, max_size=50)


def cached(cache: TTLCache, key_prefix: str = ""):
    """Decorator that caches function results.

    Only caches successful results (exceptions are not cached).
    The ``ctx`` parameter is excluded from cache key generation so that
    calls with different Context objects still hit the same cache entry.
    """
    def decorator(func):
        sig = inspect.signature(func)

        @wraps(func)
        async def wrapper(*args, **kwargs):
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            all_args = dict(bound.arguments)
            key_args = {
                k: v for k, v in all_args.items() if k != "ctx"
            }
            key = f"{key_prefix}{func.__name__}:{str(sorted(key_args.items()))}"
            cached_result = cache.get(key)
            if cached_result is not None:
                return cached_result
            result = await func(*args, **kwargs)
            cache.set(key, result)
            return result
        return wrapper
    return decorator
