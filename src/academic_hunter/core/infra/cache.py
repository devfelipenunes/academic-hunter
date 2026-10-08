import logging
import os
from typing import Optional

from .sqlite_conn import connection

logger = logging.getLogger("academic_hunter.cache")

DEFAULT_TTL_SECONDS = 7 * 24 * 60 * 60

class SQLiteCache:
    """Thread-safe persistent request caching using SQLite3.

    Connections go through ``sqlite_conn.connection`` so that WAL journalling
    and a busy timeout are applied — without them this cache is not in fact safe
    for the concurrent access its callers make — and so that each one is closed
    at the end of its block rather than whenever the collector gets to it.

    Entries expire. The table always carried a ``timestamp`` and nothing ever
    read it, so a response written once was served for the life of the database:
    one bad page cached under a query URL stayed there, and every later run read
    it back, failed in the same place, and never re-asked the API that would have
    answered correctly. A week is long enough that a repeated run costs nothing
    and short enough that the cache cannot outlive the thing it describes.
    """
    def __init__(self, db_path="results/request_cache.db", ttl_seconds: Optional[int] = DEFAULT_TTL_SECONDS):
        self.db_path = db_path
        self.ttl_seconds = ttl_seconds
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with connection(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def get(self, key: str) -> str:
        """The cached value, or None — which is also what a broken cache returns.

        Both are None by contract, so the failure is logged rather than swallowed:
        a cache answering None to everything just looks like a slow run.

        An expired entry reads as a miss and is left for the next ``set`` to
        overwrite. ``ttl_seconds=None`` disables expiry.
        """
        try:
            with connection(self.db_path) as conn:
                cursor = conn.cursor()
                if self.ttl_seconds is None:
                    cursor.execute("SELECT value FROM cache WHERE key = ?", (key,))
                else:
                    cursor.execute(
                        "SELECT value FROM cache WHERE key = ? "
                        "AND timestamp >= datetime('now', ?)",
                        (key, f"-{int(self.ttl_seconds)} seconds"),
                    )
                row = cursor.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.warning("Cache read error (treating as a miss): %s", e)
            return None

    def set(self, key: str, value: str):
        try:
            with connection(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO cache (key, value, timestamp) VALUES (?, ?, CURRENT_TIMESTAMP)",
                    (key, value)
                )
                conn.commit()
        except Exception as e:
            logger.warning("Cache write error: %s", e)
