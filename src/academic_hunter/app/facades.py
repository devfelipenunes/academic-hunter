import re
from typing import Dict, Any, List
from urllib.parse import urlsplit

class HunterFacadeMixin:
    """
    Mixin that encapsulates all backward-compatible properties, setters, and facade 
    delegation methods for the AcademicHunter engine.
    """

    @property
    def settings(self) -> Dict[str, Any]:
        return self.config.settings

    @property
    def anchors(self) -> Dict[str, list]:
        return self.config.anchors

    @anchors.setter
    def anchors(self, val):
        self.config.anchors = val
        self.scorer.anchors = val
        self.scorer.anchor_patterns = {
            t: re.compile(rf'\b{re.escape(t.lower())}\b')
            for cat in val.values() for t in cat
        }

    @property
    def tech_strings(self) -> Dict[str, list]:
        return self.config.tech_strings

    @tech_strings.setter
    def tech_strings(self, val):
        self.config.tech_strings = val
        self.scorer.tech_strings = val
        self.scorer.tech_term_patterns = {
            t: re.compile(rf'\b{re.escape(t.lower())}\b')
            for cat in val.values() for t in cat
        }

    @property
    def tech_weights(self) -> Dict[str, float]:
        return self.config.tech_weights

    @tech_weights.setter
    def tech_weights(self, val):
        self.config.tech_weights = val
        self.scorer.tech_weights = val
        self.scorer.compiled_patterns = {
            t: (re.compile(rf'\b{re.escape(t.lower())}\b'), w)
            for t, w in val.items()
        }

    @property
    def pacing_delays(self) -> Dict[str, float]:
        return self.config.pacing_delays

    @pacing_delays.setter
    def pacing_delays(self, val):
        self.config.pacing_delays = val
        for conn in self.connectors.values():
            conn.pacing_delays = val

    _pacing_delays = pacing_delays

    @property
    def blocked_sources(self) -> set:
        return self.config.blocked_sources

    @blocked_sources.setter
    def blocked_sources(self, val):
        self.config.blocked_sources = val
        for conn in self.connectors.values():
            conn.blocked_sources = val

    @property
    def stats(self): return self.state.stats
    @stats.setter
    def stats(self, val): self.state.stats = val

    @property
    def consolidated_results(self): return self.state.consolidated_results
    @consolidated_results.setter
    def consolidated_results(self, val): self.state.consolidated_results = val

    @property
    def seen_ids(self): return self.state.seen_ids
    @seen_ids.setter
    def seen_ids(self, val): self.state.seen_ids = val

    @property
    def seen_dois(self): return self.state.seen_dois
    @seen_dois.setter
    def seen_dois(self, val): self.state.seen_dois = val

    @property
    def doi_to_slug(self): return self.state.doi_to_slug

    @property
    def query_history(self): return self.state.query_history

    @property
    def last_request_time(self): return self.state.last_request_time
    @last_request_time.setter
    def last_request_time(self, val): self.state.last_request_time = val

    @property
    def last_request_by_domain(self): return self.state.last_request_by_domain
    @last_request_by_domain.setter
    def last_request_by_domain(self, val):
        self.state.last_request_by_domain = val
        for conn in self.connectors.values():
            conn.last_request_by_domain = val

    @property
    def compiled_patterns(self): return self.scorer.compiled_patterns
    @compiled_patterns.setter
    def compiled_patterns(self, val): self.scorer.compiled_patterns = val

    @property
    def anchor_patterns(self): return self.scorer.anchor_patterns
    @anchor_patterns.setter
    def anchor_patterns(self, val): self.scorer.anchor_patterns = val

    def calculate_score(self, title: str, abstract: str, citations: int = 0) -> float:
        return self.scorer.calculate_score(title, abstract, citations)

    def generate_slug(self, title: str) -> str:
        return self.scorer.generate_slug(title)

    def normalize_anchor(self, term: str) -> str:
        return self.scorer.normalize_anchor(term)

    def find_matching_terms(self, text: str, terms_list: List[str]) -> str:
        return self.scorer.find_matching_terms(text, terms_list)

    def _make_request(self, url: str, params: Dict[str, Any] = None, timeout: int = 20, max_retries: int = 2) -> Any:
        """Send a request through the connector that owns the URL's host.

        Routing by host is a security concern, not just a tidiness one. Each
        connector's ``get_headers()`` may attach its own credential — OpenAlex
        sends ``Authorization: Bearer <key>``, Semantic Scholar sends
        ``x-api-key``. This method used to dispatch every URL through the
        OpenAlex connector regardless of destination, so the OpenAlex API key
        travelled to whichever host the caller named: arXiv, Crossref, Semantic
        Scholar. It only fires when a key is configured, which is why it went
        unnoticed.

        Pacing was never affected — ``BaseConnector._raw_request`` derives the
        domain from the URL — so the damage was confined to the credentials.

        Raises:
            ValueError: If no configured connector owns the host. Refusing is
                the point: the alternative is borrowing another source's
                identity, which is what this method used to do.
        """
        host = urlsplit(url).netloc
        for connector in self.connectors.values():
            if getattr(connector, "domain", "") == host:
                return connector._make_request(url, params, timeout, max_retries)

        raise ValueError(
            f"No connector owns host {host!r}; refusing to send the request "
            f"under another source's credentials."
        )

    def load_config(self):
        self.config.load()

    def fetch_abstract_by_doi(self, doi: str) -> str:
        from ..core.pipeline import AbstractEnricher
        return AbstractEnricher(self.connectors, self.state, self.lock).fetch_abstract_by_doi(doi)

    def enrich_missing_abstracts(self):
        from ..core.pipeline import AbstractEnricher
        AbstractEnricher(self.connectors, self.state, self.lock).enrich()

    def _process_paper(self, paper: Dict, anchor_cat: str, tech_cat: str, anchor_list: List[str], tech_list: List[str]):
        self.processor.process(paper, anchor_cat, tech_cat, anchor_list, tech_list)

    def _api_worker(self, source_name: str, fetch_func=None, limit_per_source: int = 100):
        self.pipeline._api_worker(source_name, fetch_func, limit_per_source)

    def run(self, limit_per_source: int = 100) -> str:
        return self.pipeline.run(limit_per_source)

# Helper decorator to bind fetch facades dynamically on the Mixin
def _register_facades():
    from ..plugins.connectors import CONNECTORS as _CONNECTORS
    for name, connector_cls in _CONNECTORS.items():
        suffix = getattr(connector_cls, 'fetch_suffix', name.lower().replace(" ", "_"))
        def _create_facade(s=suffix, n=name):
            def facade(self, anchors, tech_strings, limit=50):
                return self.connectors[n].fetch(anchors, tech_strings, limit)
            return facade
        setattr(HunterFacadeMixin, f"fetch_{suffix}", _create_facade())

_register_facades()
