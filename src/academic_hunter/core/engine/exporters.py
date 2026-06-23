import logging

logger = logging.getLogger("academic_hunter")

class HunterExporterMixin:
    """Mixin focused exclusively on generating reports and coordinating export plugins."""
    def generate_prisma_report(self, timestamp: str):
        from ...plugins.exporters.base import ExportContext
        from ...plugins.exporters import EXPORTERS
        ctx = ExportContext(
            papers=list(self.consolidated_results.values()),
            stats=self.stats,
            settings=self.config.settings,
            query_history=self.state.query_history,
            anchors=self.config.anchors,
            tech_strings=self.config.tech_strings,
            timestamp=timestamp,
            output_dir=self.output_dir
        )
        for exporter in EXPORTERS:
            if getattr(exporter, "is_prisma", False):
                exporter.export(ctx)
                break

    def export_results(self, timestamp: str):
        from ...plugins.exporters.base import ExportContext
        from ...plugins.exporters import EXPORTERS
        papers_list = list(self.consolidated_results.values())
        ctx = ExportContext(
            papers=papers_list,
            stats=self.stats,
            settings=self.config.settings,
            query_history=self.state.query_history,
            anchors=self.config.anchors,
            tech_strings=self.config.tech_strings,
            timestamp=timestamp,
            output_dir=self.output_dir
        )
        for exporter in EXPORTERS:
            if not getattr(exporter, "is_prisma", False):
                try:
                    exporter.export(ctx)
                except Exception as e:
                    logger.error(f"Failed to export via {exporter.__class__.__name__}: {e}")
