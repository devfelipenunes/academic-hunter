"""Academic Hunter — Automated scholarly article aggregation and ranking."""

__version__ = "2.1.0"

import logging

from .app import AcademicHunter
from .core.infra import HunterConfig, SearchState, SQLiteCache
from .core.models import Paper
from .core.nlp import AcademicScorer
from .core.ports import BaseScreener, BaseVectorStore

try:
    from .plugins.vector_stores import ChromaVectorStore
    _has_vector_store = True
except ImportError:
    ChromaVectorStore = None  # type: ignore
    _has_vector_store = False

try:
    from .plugins.screeners import SemanticScreener
    _has_semantic_screener = True
except ImportError:
    SemanticScreener = None  # type: ignore
    _has_semantic_screener = False

logging.getLogger("academic_hunter").addHandler(logging.NullHandler())

__all__ = [
    "AcademicHunter",
    "Paper",
    "AcademicScorer",
    "SQLiteCache",
    "HunterConfig",
    "SearchState",
    "ChromaVectorStore",
    "BaseVectorStore",
    "SemanticScreener",
    "BaseScreener",
]
