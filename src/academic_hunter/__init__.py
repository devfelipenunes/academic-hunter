"""Academic Hunter — Automated scholarly article aggregation and ranking."""

__version__ = "2.0.0"

import logging

from .core.engine import AcademicHunter
from .core.models import Paper
from .core.nlp import AcademicScorer
from .core.infra import SQLiteCache
from .core.infra import HunterConfig
from .core.infra import SearchState

# Configure a NullHandler so library users can set their own logging config
logging.getLogger("academic_hunter").addHandler(logging.NullHandler())

__all__ = [
    "AcademicHunter",
    "Paper",
    "AcademicScorer",
    "SQLiteCache",
    "HunterConfig",
    "SearchState",
]
