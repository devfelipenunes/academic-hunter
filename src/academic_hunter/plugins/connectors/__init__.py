"""
Connector plugin package — auto-discovered connector classes.

Each ``.py`` file in this directory (except ``_*.py`` files and the base module)
is imported and scanned for ``BaseConnector`` subclasses, which are then
registered in the ``CONNECTORS`` dictionary keyed by their display name.
"""

import importlib
from pathlib import Path

from .base import BaseConnector  # noqa: F401 — re-exported for convenience

CONNECTORS: dict = {}

# Mapping from module name (stem) to connector display name.
# Kept explicit to preserve backward-compatible keys ("ArXiv", "CORE", …)
# while avoiding imports of every connector at the package level.
_CONNECTOR_NAMES: dict[str, str] = {
    "arxiv": "ArXiv",
    "crossref": "Crossref",
    "openalex": "OpenAlex",
    "semanticscholar": "Semantic Scholar",
    "core_ac": "CORE",
    "dblp": "DBLP",
    "doaj": "DOAJ",
}


def _discover_connectors() -> None:
    """Auto-discover connector classes by scanning every ``*.py`` file.

    Skips private modules (``_*.py``) and the ``base.py`` module.
    Each discovered ``BaseConnector`` subclass is registered under its
    display name (from ``_CONNECTOR_NAMES``) in the ``CONNECTORS`` dict.
    """
    pkg_dir = Path(__file__).resolve().parent
    for f in sorted(pkg_dir.glob("*.py")):
        if f.name.startswith("_") or f.name == "base.py":
            continue
        module_name = f.stem
        module = importlib.import_module(f".{module_name}", __package__)
        for attr_name in dir(module):
            cls = getattr(module, attr_name)
            if not isinstance(cls, type):
                continue
            if not issubclass(cls, BaseConnector) or cls is BaseConnector:
                continue
            display_name = _CONNECTOR_NAMES.get(module_name)
            if display_name:
                CONNECTORS[display_name] = cls


_discover_connectors()
