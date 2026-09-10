"""Screener plugins for paper relevance evaluation.

Only the semantic screener is wired into the pipeline. Keyword scoring lives in
``core.nlp.AcademicScorer`` and is not duplicated here: a ``KeywordScreener``
stub used to sit alongside it returning a constant ``1.0``, and a ``SCREENERS``
registry mapped names to classes that nothing ever looked up.
"""

from .base import BaseScreener
from .semantic import SemanticScreener

__all__ = [
    "BaseScreener",
    "SemanticScreener",
]
