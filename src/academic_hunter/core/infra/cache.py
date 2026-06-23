import os
import sqlite3

class SQLiteCache:
    """Thread-safe persistent request caching using SQLite3."""
    def __init__(self, db_path="results/request_cache.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()
        
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            
    def get(self, key: str) -> str:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM cache WHERE key = ?", (key,))
                row = cursor.fetchone()
                return row[0] if row else None
        except Exception:
            return None
            
    def set(self, key: str, value: str):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO cache (key, value, timestamp) VALUES (?, ?, CURRENT_TIMESTAMP)", 
                    (key, value)
                )
                conn.commit()
        except Exception as e:
            print(f"Cache write error: {e}")
