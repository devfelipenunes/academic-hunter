import threading
from pathlib import Path
from typing import Dict, Any, Optional

from ..infra import SQLiteCache, HunterConfig, SearchState
from ..nlp import AcademicScorer
from .facades import HunterFacadeMixin
from .exporters import HunterExporterMixin


class AcademicHunter(HunterFacadeMixin, HunterExporterMixin):
    """
    AcademicHunter is an automated research tool that aggregates scholarly articles
    from multiple APIs. It filters results based on exact anchor matches and ranks them
    using a technical elite score.

    Accepts optional ``connectors`` and ``semantic_screener`` params for dependency
    injection (useful in tests). Defaults to auto-discovering plugins from the
    plugin registry.
    """

    def __init__(self, config_path: str = 'config.json', output_dir: str = 'results',
                 use_cache: bool = True, connectors: Optional[Dict[str, Any]] = None,
                 semantic_screener: Any = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

        import sys
        is_testing = 'pytest' in sys.modules or 'unittest' in sys.modules or 'test' in str(config_path).lower()
        self.use_cache = use_cache and not is_testing

        self.cache = SQLiteCache(db_path=str(self.output_dir / "request_cache.db"))
        self.lock = threading.RLock()
        self.semaphore = threading.Semaphore(2)

        # Core components — access via hunter.config, hunter.state, hunter.scorer
        self.config = HunterConfig(config_path)
        self.state = SearchState()
        self.scorer = AcademicScorer(
            self.config.anchors, self.config.tech_strings,
            self.config.tech_weights, self.config.context_rules, self.config.settings
        )

        # Semantic screener — injectable for tests, lazy import as default
        if semantic_screener is not None:
            self.semantic_screener = semantic_screener
        else:
            from ...plugins.screeners import SemanticScreener as _SemanticScreener
            self.semantic_screener = _SemanticScreener()

        # Connectors — injectable for tests, plugin registry as default
        if connectors is not None:
            self.connectors = connectors
        else:
            from ...plugins.connectors import CONNECTORS as _CONNECTORS
            conn_args = (self.cache, self.config.settings, self.state.query_history,
                         self.lock, self.semaphore, self.use_cache)
            self.connectors = {
                name: cls(*conn_args) for name, cls in _CONNECTORS.items()
            }

        # Propagate shared mutable state to the connectors
        for conn in self.connectors.values():
            conn.pacing_delays = self.config.pacing_delays
            conn.last_request_by_domain = self.state.last_request_by_domain
            conn.blocked_sources = self.config.blocked_sources
            conn.setup_pacing()

        from ..screening import PaperProcessor
        self.processor = PaperProcessor(self.state, self.scorer, self.config, self.connectors, self.lock, self.semantic_screener)

        from ..pipeline import SearchPipeline
        self.pipeline = SearchPipeline(self)
