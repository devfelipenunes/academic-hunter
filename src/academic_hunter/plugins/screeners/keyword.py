from .base import BaseScreener
from typing import Dict, Any

class KeywordScreener(BaseScreener):
    """
    Classic Heuristic Screener based on strict string matching and keyword counting.
    (Currently the default behavior of Academic Hunter V2)
    """
    
    def evaluate(self, paper_data: Dict[str, Any], config: Dict[str, Any]) -> float:
        # TODO: Migrate existing core/nlp/screening.py logic here
        return 1.0
