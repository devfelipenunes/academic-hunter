"""Ports — the interfaces the domain defines and the adapters implement.

Dependencies point inwards: ``plugins`` import from here, and ``core`` never
imports a concrete plugin. The composition root (``academic_hunter.hunter``)
is the only place that knows both sides and wires them together.

``BaseConnector`` is deliberately *not* here: it is a concrete HTTP
implementation, not a port. What the domain needs from a connector is the
narrow ``ConnectorPort`` protocol below.
"""

from .connector import ConnectorPort
from .exporter import BaseExporter, ExportContext
from .fulltext import (
    ExtractedDocument,
    FullTextConfigError,
    FullTextError,
    FullTextSourcePort,
    FullTextTransientError,
    NoOpenAccessVersion,
    OpenAccessLocation,
    TextExtractorPort,
)
from .screener import BaseScreener
from .vector_store import BaseVectorStore, ChunkStorePort

__all__ = [
    "ConnectorPort",
    "BaseExporter",
    "ExportContext",
    "BaseScreener",
    "BaseVectorStore",
    "ChunkStorePort",
    "ExtractedDocument",
    "FullTextConfigError",
    "FullTextError",
    "FullTextSourcePort",
    "FullTextTransientError",
    "NoOpenAccessVersion",
    "OpenAccessLocation",
    "TextExtractorPort",
]
