"""Config change history tracking — extracted from HunterConfig.

Tracks config snapshots for MCP undo/restore functionality.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ConfigSnapshot:
    """Immutable snapshot of config state for history tracking."""
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0


class ConfigHistory:
    """Manages a rolling history of config snapshots.

    This is a record only — ``push()`` stores snapshots and ``list_history()``
    exposes them. Restoring is handled by the MCP ``restore_config_by_id`` tool,
    which reads the SQLite backup written by ``MCPDatabaseManager``; a
    ``restore(snapshot_id)`` method used to live here and returned ``True``
    without restoring anything, which is worse than not having it.
    """

    _history: List[ConfigSnapshot] = []
    _max_history: int = 20

    @classmethod
    def push(cls, snapshot_data: Dict[str, Any]) -> None:
        """Store a config snapshot for undo/restore functionality."""
        cls._history.append(ConfigSnapshot(
            data=snapshot_data,
            timestamp=time.time(),
        ))
        if len(cls._history) > cls._max_history:
            cls._history.pop(0)

    @classmethod
    def list_history(cls) -> List[Dict[str, Any]]:
        """Get config change history for MCP tool display."""
        return [
            {
                "id": i,
                "timestamp": snap.timestamp,
                "data": snap.data,
            }
            for i, snap in enumerate(cls._history)
        ]

    @classmethod
    def clear(cls) -> None:
        """Clear all history (useful for testing)."""
        cls._history.clear()
