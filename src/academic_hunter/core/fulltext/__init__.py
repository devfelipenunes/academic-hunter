"""Full-text handling: turning a paper's body into retrievable fragments."""

from .chunker import Chunk, Section, chunk_document, detect_sections

__all__ = ["Chunk", "Section", "chunk_document", "detect_sections"]
