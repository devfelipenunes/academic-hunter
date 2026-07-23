"""Vector store plugins for semantic search (RAG)."""

from .base import BaseVectorStore
from .chroma import ChromaVectorStore

VECTOR_STORES = {
    "chroma": ChromaVectorStore,
}

__all__ = [
    "BaseVectorStore",
    "ChromaVectorStore",
    "VECTOR_STORES",
]
