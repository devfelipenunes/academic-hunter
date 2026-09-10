"""Vector store plugins for semantic search (RAG).

``ChromaVectorStore`` is instantiated directly by the pipeline; a
``VECTOR_STORES`` name-to-class registry used to sit here, but nothing ever
looked anything up in it.
"""

from .base import BaseVectorStore
from .chroma import ChromaVectorStore

__all__ = [
    "BaseVectorStore",
    "ChromaVectorStore",
]
