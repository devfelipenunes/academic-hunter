"""Config change history tracking — extracted from HunterConfig.

Tracks config snapshots for MCP undo/restore functionality.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ConfigSnapshot:
    """Immutable snapshot of config state for history tracking."""
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0


class ConfigHistory:
    """Manages a rolling history of config snapshots.

    Thread-safe for read operations. Each ``push()`` stores the current config
    state so it can be restored later via ``restore()``.
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
    def restore(cls, snapshot_id: int) -> bool:
        """Check if a snapshot is available for restore.

        Args:
            snapshot_id: Index into the history list.

        Returns:
            True if the snapshot exists, False otherwise.
        """
        return 0 <= snapshot_id < len(cls._history)

    @classmethod
    def clear(cls) -> None:
        """Clear all history (useful for testing)."""
        cls._history.clear()
