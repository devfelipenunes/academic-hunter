"""Connector port — what the domain needs from a scholarly source adapter.

This is a ``Protocol`` rather than an ABC on purpose. ``BaseConnector`` in
``plugins/connectors`` is a concrete HTTP implementation (requests, retries,
caching, pacing) and belongs with the adapters; forcing it to inherit from a
domain ABC would drag transport concerns into ``core``. Structural typing lets
the domain depend on the *shape* it uses without owning the implementation.

Two capabilities are optional rather than mandatory, which structural typing
alone cannot express: ``resolve_priority`` decides whether a source is asked to
resolve anything at all, and ``resolve_metadata_by_doi`` decides whether it can.
Both are read with a default by their caller rather than enforced here, because
a silently ignored method is the failure mode this port cannot detect.
"""

from typing import Any, Dict, List, Protocol, runtime_checkable


@runtime_checkable
class ConnectorPort(Protocol):
    """Minimal surface the pipeline uses on a source connector."""

    fetch_suffix: str
    domain: str
    default_delay: float
    resolve_priority: int

    pacing_delays: Dict[str, float]
    last_request_by_domain: Dict[str, float]
    blocked_sources: set

    def fetch(
        self, anchors: List[str], tech_strings: List[str], limit: int
    ) -> List[Dict[str, Any]]:
        """Query the source and return raw paper dictionaries.

        ``anchors`` and ``tech_strings`` are flat term lists — one category at a
        time — not the config's category-to-terms maps. The worker walks the
        categories and calls this once per pair, so the connector has nothing to
        do with the grouping. ``runtime_checkable`` only checks that a method
        exists, never its signature, so a port that described a map here was
        wrong in silence.
        """
        ...

    def resolve_metadata_by_doi(self, doi: str) -> Dict[str, Any]:
        """Return what the source knows about a DOI, keyed by field name.

        ``Abstract`` and ``Citations`` are the keys a resolver may return, and a
        source that knows only one returns only that one — an absent key means
        "not known here", never zero. A source that returns ``{}`` is one that
        has nothing to contribute by DOI and is simply skipped by the enricher.

        ``resolve_abstract_by_doi`` remains the narrower contract for callers
        that want the text alone; ``BaseConnector`` implements it in terms of
        this method, so a source only ever overrides one of the two.
        """
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

    @classmethod
    def unavailable_reason(cls, settings: Dict[str, Any]) -> str:
        """Why the connector cannot run with these settings, or an empty string."""
        ...
