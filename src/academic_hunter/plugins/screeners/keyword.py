from .base import BaseScreener
from typing import Dict, Any

class KeywordScreener(BaseScreener):
    """Keyword matching screener (plugin interface)."""

    def evaluate(self, paper_data: Dict[str, Any], config: Dict[str, Any]) -> float:
        return 1.0
