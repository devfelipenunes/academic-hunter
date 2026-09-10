"""Exporter base — re-exported from the domain port.

The contract lives in ``core.ports.exporter`` so that ``core`` can depend on it
without importing a plugin. Adapters import it from here for convenience.
"""

from ...core.ports.exporter import BaseExporter, ExportContext

__all__ = ["BaseExporter", "ExportContext"]
