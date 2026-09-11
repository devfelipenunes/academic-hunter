import logging
import os

from .sqlite_conn import connect

logger = logging.getLogger("academic_hunter.cache")

class SQLiteCache:
    """Thread-safe persistent request caching using SQLite3.

    Connections go through ``sqlite_conn.connect`` so that WAL journalling and
    a busy timeout are applied — without them this cache is not in fact safe
    for the concurrent access its callers make.
    """
    def __init__(self, db_path="results/request_cache.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with connect(self.db_path) as conn:
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
        """
        try:
            with connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM cache WHERE key = ?", (key,))
                row = cursor.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.warning("Cache read error (treating as a miss): %s", e)
            return None

    def set(self, key: str, value: str):
        try:
            with connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO cache (key, value, timestamp) VALUES (?, ?, CURRENT_TIMESTAMP)",
                    (key, value)
                )
                conn.commit()
        except Exception as e:
            logger.warning("Cache write error: %s", e)
