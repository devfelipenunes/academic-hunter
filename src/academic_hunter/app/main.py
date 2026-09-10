import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional

from ..core.infra import SQLiteCache, HunterConfig, SearchState
from ..core.nlp import AcademicScorer
from .facades import HunterFacadeMixin
from .exporters import HunterExporterMixin

logger = logging.getLogger("academic_hunter.app")


class AcademicHunter(HunterFacadeMixin, HunterExporterMixin):
    """
    AcademicHunter is an automated research tool that aggregates scholarly articles
    from multiple APIs. It filters results based on exact anchor matches and ranks them
    using a technical elite score.

    This is the **composition root**: the only place that imports concrete plugins
    and wires them into the domain. Every collaborator can be injected — tests use
    that to substitute fakes, and it is what keeps ``core`` free of any dependency
    on ``plugins`` or ``interfaces``.
    """

    def __init__(self, config_path: str = 'config.json', output_dir: str = 'results',
                 use_cache: bool = True, connectors: Optional[Dict[str, Any]] = None,
                 semantic_screener: Any = None,
                 exporters: Optional[list] = None,
                 vector_store_factory: Any = None,
                 obsidian_export: Any = None,
                 full_text_fetcher: Any = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

        import sys
        is_testing = 'pytest' in sys.modules or 'unittest' in sys.modules or 'test' in str(config_path).lower()
        self.use_cache = use_cache and not is_testing

        self.cache = SQLiteCache(db_path=str(self.output_dir / "request_cache.db"))
        self.lock = threading.RLock()
        self.semaphore = threading.Semaphore(2)

        # Pacing defaults are a property of the adapter set, so they are read from
        # the connectors here and handed to the config — the config itself no
        # longer reaches into the plugin registry to discover them.
        connector_classes = self._resolve_connector_classes(connectors)

        # Core components — access via hunter.config, hunter.state, hunter.scorer
        self.config = HunterConfig(
            config_path, pacing_defaults=self._pacing_defaults(connector_classes)
        )
        self.state = SearchState()
        self.scorer = AcademicScorer(
            self.config.anchors, self.config.tech_strings,
            self.config.tech_weights, self.config.context_rules, self.config.settings
        )

        # Semantic screener — injectable for tests, plugin import as default
        if semantic_screener is not None:
            self.semantic_screener = semantic_screener
        else:
            from ..plugins.screeners import SemanticScreener as _SemanticScreener
            self.semantic_screener = _SemanticScreener()

        # Connectors — injectable for tests, plugin registry as default
        if connectors is not None:
            self.connectors = connectors
        else:
            conn_args = (self.cache, self.config.settings, self.state.query_history,
                         self.lock, self.semaphore, self.use_cache)
            self.connectors = {
                name: cls(*conn_args) for name, cls in connector_classes.items()
            }

        # Propagate shared mutable state to the connectors
        for conn in self.connectors.values():
            conn.pacing_delays = self.config.pacing_delays
            conn.last_request_by_domain = self.state.last_request_by_domain
            conn.blocked_sources = self.config.blocked_sources
            conn.setup_pacing()

        # Exporters — injectable, plugin registry as default
        if exporters is not None:
            self.exporters = exporters
        else:
            from ..plugins.exporters import EXPORTERS as _EXPORTERS
            self.exporters = _EXPORTERS

        # Vector store — injected factory, lazy ChromaDB as default. The pipeline
        # asks for the factory instead of importing the adapter.
        if vector_store_factory is not None:
            self.vector_store_factory = vector_store_factory
        else:
            from ..plugins.vector_stores import ChromaVectorStore

            def _chroma_factory(db_dir: Path):
                return ChromaVectorStore(db_dir=str(db_dir))

            self.vector_store_factory = _chroma_factory

        # Obsidian auto-export — injected callable, plugin adapter as default.
        # The pipeline step must not import the MCP tool layer.
        if obsidian_export is not None:
            self.obsidian_export = obsidian_export
        else:
            from ..plugins.exporters.obsidian import write_obsidian_note

            def _obsidian_export(topic: str, content: str, tags: list, vault_path: str):
                return f"✅ Report exported to Obsidian: " + str(
                    write_obsidian_note(
                        vault_path=vault_path, topic=topic, content=content, tags=tags
                    )
                )

            self.obsidian_export = _obsidian_export

        # Full text — injected callable, adapters as default. Whether it runs at
        # all is `settings.fulltext.enabled`, which the step checks; building it
        # here only means the capability exists.
        if full_text_fetcher is not None:
            self.full_text_fetcher = full_text_fetcher
        else:
            self.full_text_fetcher = self._build_full_text_fetcher()

        from ..core.screening import PaperProcessor
        self.processor = PaperProcessor(self.state, self.scorer, self.config, self.connectors, self.lock, self.semantic_screener)

        from ..core.pipeline import SearchPipeline
        self.pipeline = SearchPipeline(self)

    def _build_full_text_fetcher(self):
        """Compose locate → download → extract into a single callable.

        Returns ``None`` when the pieces cannot be built — no contact e-mail, or
        an address Unpaywall would refuse. The step reads ``None`` as "not
        wired" and skips, which is the outcome of the feature being off.
        """
        from ..core.ports.fulltext import FullTextConfigError
        from ..plugins.fulltext.cache import CachedFullTextSource, PdfCache
        from ..plugins.fulltext.pdf import PdfExtractor
        from ..plugins.fulltext.unpaywall import UnpaywallSource

        try:
            source = UnpaywallSource(self.config.fulltext_config()["email"])
        except FullTextConfigError as e:
            logger.info("Full-text fetching unavailable: %s", e)
            return None

        cached = CachedFullTextSource(
            source,
            PdfCache(Path(self.output_dir).parent / ".academic_hunter" / "fulltext"),
        )
        extractor = PdfExtractor()

        def fetch(doi: str) -> Any:
            return extractor.extract(cached.download(cached.locate(doi)))

        return fetch

    @staticmethod
    def _resolve_connector_classes(connectors: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Return the connector *classes* to instantiate, or ``{}`` when injected.

        When connectors are supplied already-built, pacing defaults come from the
        instances instead of a registry lookup.
        """
        if connectors is not None:
            return {name: type(conn) for name, conn in connectors.items()}
        from ..plugins.connectors import CONNECTORS as _CONNECTORS
        return _CONNECTORS

    @staticmethod
    def _pacing_defaults(connector_classes: Dict[str, Any]) -> Dict[str, float]:
        """Map each connector's host domain to its default request delay."""
        delays: Dict[str, float] = {}
        for cls in connector_classes.values():
            domain = getattr(cls, 'domain', '')
            if domain:
                delays[domain] = getattr(cls, 'default_delay', 1.5)
        return delays
