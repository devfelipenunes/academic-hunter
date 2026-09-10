import logging

from ..core.ports import ExportContext

logger = logging.getLogger("academic_hunter")


class HunterExporterMixin:
    """Mixin focused exclusively on generating reports and coordinating export plugins.

    The exporter list arrives by injection (``AcademicHunter(exporters=...)``).
    This module used to import the concrete ``plugins.exporters.EXPORTERS``
    registry, which meant the domain knew about its adapters.
    """

    def _export_context(self, timestamp: str) -> ExportContext:
        """Build the context every exporter receives."""
        return ExportContext(
            papers=list(self.consolidated_results.values()),
            stats=self.stats,
            settings=self.config.settings,
            query_history=self.state.query_history,
            anchors=self.config.anchors,
            tech_strings=self.config.tech_strings,
            timestamp=timestamp,
            output_dir=self.output_dir,
        )

    def generate_prisma_report(self, timestamp: str):
        ctx = self._export_context(timestamp)
        for exporter in self.exporters:
            if getattr(exporter, "is_prisma", False):
                exporter.export(ctx)
                break

    def export_results(self, timestamp: str):
        ctx = self._export_context(timestamp)
        for exporter in self.exporters:
            if not getattr(exporter, "is_prisma", False):
                try:
                    exporter.export(ctx)
                except Exception as e:
                    logger.error(f"Failed to export via {exporter.__class__.__name__}: {e}")
