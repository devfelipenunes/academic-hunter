"""Vector store base — re-exported from the domain port.

The contract lives in ``core.ports.vector_store`` so that ``core`` can depend on
it without importing a plugin. Adapters import it from here for convenience.
"""

from ...core.ports.vector_store import BaseVectorStore

__all__ = ["BaseVectorStore"]
