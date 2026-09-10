"""Screener base — re-exported from the domain port.

The contract lives in ``core.ports.screener`` so that ``core`` can depend on it
without importing a plugin. Adapters import it from here for convenience.
"""

from ...core.ports.screener import BaseScreener

__all__ = ["BaseScreener"]
