"""Shared utilities and constants for MCP tools.

* ``get_project_root()`` — resolves paths relative to the project root.
* ``_STOPWORDS`` — common English academic-stopwords used by several tools.
* ``_get_vector_store()`` — initialises a ChromaDB vector-store instance.
"""

import logging
from pathlib import Path

from academic_hunter import AcademicHunter
from academic_hunter.plugins.vector_stores import ChromaVectorStore

import academic_hunter as pkg

logger = logging.getLogger("academic_hunter.mcp._utils")

_STOPWORDS = {
    "the", "a", "an", "of", "in", "for", "and", "or", "to", "with",
    "on", "at", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "but",
    "not", "what", "which", "who", "whom", "this", "that", "these",
    "those", "it", "its", "study", "research", "paper", "approach",
    "method", "result", "analysis", "based", "using", "new", "novel",
}


def get_project_root() -> Path:
    """
    Resolve the academic-hunter project root from the package location,
    NOT from the current working directory.

    The package is installed as an editable wheel (``pip install -e``), so
    ``academic_hunter.__file__`` points at the real ``src/`` tree.  We walk
    upward until ``pyproject.toml`` is found — that's the project root.

    This decouples output paths (results/, chroma_db/, …) from wherever the
    MCP server process happens to be launched.
    """
    pkg_init = Path(pkg.__file__).resolve()
    for parent in [pkg_init] + list(pkg_init.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    # Safety net — should never fire in a proper install
    return Path.cwd()


def _get_vector_store() -> ChromaVectorStore | None:
    """Initialize the ChromaDB vector store (same pattern as rag.py)."""
    try:
        hunter = AcademicHunter(output_dir=str(get_project_root() / "results"))
        db_dir = str(hunter.output_dir.parent / ".academic_hunter" / "chroma_db")
        return ChromaVectorStore(db_dir=db_dir)
    except Exception:
        return None
