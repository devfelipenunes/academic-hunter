"""Screener plugins for paper relevance evaluation."""

from .base import BaseScreener
from .keyword import KeywordScreener
from .semantic import SemanticScreener

SCREENERS = {
    "keyword": KeywordScreener,
    "semantic": SemanticScreener,
}

__all__ = [
    "BaseScreener",
    "KeywordScreener",
    "SemanticScreener",
    "SCREENERS",
]
