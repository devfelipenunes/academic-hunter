"""Academic Hunter — Automated scholarly article aggregation and ranking."""

__version__ = "2.1.0"

import logging

from .app import AcademicHunter
from .core.models import Paper
from .core.nlp import AcademicScorer
from .core.infra import SQLiteCache
from .core.infra import HunterConfig
from .core.infra import SearchState
# Ports are the public contracts; the plugin modules merely implement them.
from .core.ports import BaseScreener, BaseVectorStore

# RAG plugins
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

# Configure a NullHandler so library users can set their own logging config
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
