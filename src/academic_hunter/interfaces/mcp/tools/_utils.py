"""Shared utilities and constants for MCP tools."""

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
    """Resolve the project root from the package location."""
    pkg_init = Path(pkg.__file__).resolve()
    for parent in [pkg_init] + list(pkg_init.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def _get_vector_store():
    """Initialize and return a ChromaVectorStore instance."""
    try:
        hunter = AcademicHunter(output_dir=str(get_project_root() / "results"))
        db_dir = str(hunter.output_dir.parent / ".academic_hunter" / "chroma_db")
        return ChromaVectorStore(db_dir=db_dir)
    except Exception as e:
        logger.warning("Could not initialize vector store: %s", e)
        return None


def _make_hunter() -> AcademicHunter:
    """Create an AcademicHunter rooted at the project directory."""
    return AcademicHunter(output_dir=str(get_project_root() / "results"))
