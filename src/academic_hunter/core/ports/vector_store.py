"""Vector store port: native RAG capabilities behind an interface.

The pipeline receives a factory for this, so the concrete store (ChromaDB,
LanceDB, FAISS) is chosen at the composition root rather than imported by core.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Protocol, Sequence, runtime_checkable


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


@runtime_checkable
class ChunkStorePort(Protocol):
    """Retrieval over document *fragments* rather than whole papers.

    Deliberately not folded into :class:`BaseVectorStore`. Adding these four
    methods there would make every existing store — including the mocks — fail to
    satisfy the contract, and a store that cannot do chunk retrieval is still a
    perfectly valid vector store. Callers ask with ``isinstance(store,
    ChunkStorePort)`` and degrade when the answer is no.
    """

    def index_chunks(
        self, chunks: Sequence[Dict[str, Any]], collection_name: str = "paper_chunks"
    ) -> bool:
        """Embed and store chunk records. Returns True on success."""
        ...

    def query_chunks(
        self, prompt: str, top_k: int = 10, collection_name: str = "paper_chunks"
    ) -> List[Dict[str, Any]]:
        """Return the chunks most similar to ``prompt``, with their metadata."""
        ...

    def has_chunks(self, parent_id: str, collection_name: str = "paper_chunks") -> bool:
        """Whether any chunk belonging to ``parent_id`` is already indexed."""
        ...

    def delete_chunks(
        self,
        parent_id: str,
        collection_name: str = "paper_chunks",
        *,
        keep_ids: Sequence[str] = (),
    ) -> int:
        """Remove the chunks of ``parent_id`` that are not in ``keep_ids``.

        Returns how many were removed. ``keep_ids`` is what makes a reindex safe:
        the caller indexes the replacement first and then names what it kept, so
        the store never has to guess which chunks belong to the older version.
        """
        ...
