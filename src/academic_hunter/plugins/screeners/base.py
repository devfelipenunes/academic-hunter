from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseScreener(ABC):
    """
    Abstract Base Class for screening and scoring scientific papers.
    Any new NLP or heuristic screening logic must implement this interface.
    """
    
    @abstractmethod
    def evaluate(self, paper_data: Dict[str, Any], config: Dict[str, Any]) -> float:
        """
        Evaluate the paper against the provided configuration.
        
        Args:
            paper_data: Dictionary containing paper metadata (title, abstract, etc.)
            config: Dictionary containing user configurations (anchors, weights, etc.)
            
        Returns:
            float: A relevance score (Technical Elite Score). Return 0.0 if irrelevant.
        """
        pass
