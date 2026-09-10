"""Domain core — no outward dependencies.

Nothing in this package imports ``interfaces``, ``app`` or ``plugins``. The
contracts the adapters satisfy live in ``core.ports``; implementations arrive
by injection from the composition root (``academic_hunter.app``).
"""

from .models import Paper
from .nlp import AcademicScorer
from .infra import SQLiteCache, HunterConfig, SearchState
from .ports import (
    BaseExporter,
    BaseScreener,
    BaseVectorStore,
    ConnectorPort,
    ExportContext,
)


def get_config():
    """Return a HunterConfig instance (centralized for easy future changes).

    Use this factory instead of importing ``HunterConfig`` directly.
    """
    from .infra.config import HunterConfig as _HunterConfig
    return _HunterConfig()


__all__ = [
    "Paper",
    "AcademicScorer",
    "SQLiteCache",
    "HunterConfig",
    "SearchState",
    # ports
    "BaseExporter",
    "ExportContext",
    "BaseScreener",
    "BaseVectorStore",
    "ConnectorPort",
    "get_config",
]
