"""Connector port — what the domain needs from a scholarly source adapter.

This is a ``Protocol`` rather than an ABC on purpose. ``BaseConnector`` in
``plugins/connectors`` is a concrete HTTP implementation (requests, retries,
caching, pacing) and belongs with the adapters; forcing it to inherit from a
domain ABC would drag transport concerns into ``core``. Structural typing lets
the domain depend on the *shape* it uses without owning the implementation.
"""

from typing import Any, Dict, List, Protocol, runtime_checkable


@runtime_checkable
class ConnectorPort(Protocol):
    """Minimal surface the pipeline uses on a source connector."""

    #: Attribute name suffixes for the dynamically bound ``fetch_<suffix>`` facades.
    fetch_suffix: str
    #: Host domain, used to key pacing delays.
    domain: str
    #: Default seconds between requests to ``domain``.
    default_delay: float
    #: Higher values are tried first when resolving a DOI to an abstract.
    resolve_priority: int

    # Shared mutable state, populated by the composition root after construction.
    pacing_delays: Dict[str, float]
    last_request_by_domain: Dict[str, float]
    blocked_sources: set

    def fetch(
        self, anchors: Dict[str, List[str]], tech_strings: Dict[str, List[str]], limit: int
    ) -> List[Dict[str, Any]]:
        """Query the source and return raw paper dictionaries."""
        ...

    def resolve_abstract_by_doi(self, doi: str) -> str:
        """Return the abstract for a DOI, or an empty string."""
        ...

    def detect_peer_review(self, paper_type: str) -> str:
        """Classify the paper's peer-review status."""
        ...

    def setup_pacing(self) -> None:
        """Hook for connectors to adjust their own pacing delays."""
        ...
