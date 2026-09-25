import json
from datetime import datetime
from typing import Optional, Dict, List, Any

from ....core.infra import paths
from ....core.infra.sqlite_conn import connect

class MCPDatabaseManager:
    def __init__(self, db_path: Optional[str] = None):
        if not db_path:
            db_path = str(paths.ensure_data_dir() / "mcp_history.db")
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS config_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    topic TEXT,
                    config_json TEXT NOT NULL
                )
            ''')
            conn.commit()

    def save_config(self, topic: str, config_data: Dict[str, Any]) -> Optional[int]:
        timestamp = datetime.now().isoformat()
        with connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO config_history (timestamp, topic, config_json) VALUES (?, ?, ?)',
                (timestamp, topic, json.dumps(config_data, ensure_ascii=False))
            )
            conn.commit()
            return cursor.lastrowid

    def list_configs(self, limit: int = 10) -> List[Dict[str, Any]]:
        with connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT id, timestamp, topic FROM config_history ORDER BY id DESC LIMIT ?', 
                (limit,)
            )
            return [{"id": row[0], "timestamp": row[1], "topic": row[2]} for row in cursor.fetchall()]

    def get_config(self, config_id: int) -> Optional[Dict[str, Any]]:
        with connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT config_json FROM config_history WHERE id = ?', (config_id,))
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
            return None
