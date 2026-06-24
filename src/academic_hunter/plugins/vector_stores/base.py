from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseVectorStore(ABC):
    """
    Abstract Base Class for integrating Native RAG capabilities.
    Any new Vector DB (ChromaDB, LanceDB, FAISS) must implement this interface.
    """
    
    @abstractmethod
    def index_papers(self, papers: List[Dict[str, Any]]) -> bool:
        """
        Convert paper metadata/abstracts into vector embeddings and index them.
        
        Args:
            papers: A list of paper dictionaries.
            
        Returns:
            bool: True if indexing was successful.
        """
        pass
    
    @abstractmethod
    def query(self, prompt: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Perform a semantic similarity search against the vector database.
        
        Args:
            prompt: The user's query string.
            top_k: Number of results to return.
            
        Returns:
            List[Dict[str, Any]]: A list of semantically relevant papers.
        """
        pass
