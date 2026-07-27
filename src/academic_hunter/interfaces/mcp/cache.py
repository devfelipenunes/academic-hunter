"""Simple in-memory cache for MCP tools to avoid repeated API calls.

Uses TTL-based expiration. Thread-safe for async usage.
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
            # Evict oldest
            oldest = min(self._timestamps, key=self._timestamps.get)
            del self._store[oldest]
            del self._timestamps[oldest]
        self._store[key] = value
        self._timestamps[key] = time.time()

    def clear(self):
        """Clear all cached values."""
        self._store.clear()
        self._timestamps.clear()

    @property
    def size(self) -> int:
        return len(self._store)


# Global cache instances
citation_cache = TTLCache(ttl_seconds=600, max_size=200)  # 10 min TTL
discovery_cache = TTLCache(ttl_seconds=300, max_size=100)  # 5 min TTL


def cached(cache: TTLCache, key_prefix: str = ""):
    """Decorator that caches function results.

    Only caches successful results (exceptions are not cached).
    The ``ctx`` parameter is excluded from cache key generation so that
    calls with different Context objects still hit the same cache entry.
    """
    def decorator(func):
        sig = inspect.signature(func)
        param_names = list(sig.parameters.keys())

        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Build a dict of all argument names -> values
            # so we can exclude the `ctx` parameter from the cache key.
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            all_args = dict(bound.arguments)
            # Remove ctx from key generation
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
