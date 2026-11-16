import logging

from academic_hunter.core.writing import renderers

from .base import BaseExporter, ExportContext

logger = logging.getLogger("academic_hunter.exporters")


class RisExporter(BaseExporter):
    """The run as RIS, written into the run directory.

    The text comes from ``renderers.render_ris``, which the ``export_report``
    tool also calls — the two used to render it separately, and disagreed on the
    abstract's tag.
    """

    def export(self, context: ExportContext) -> None:
        run_dir = self._get_run_dir(context.timestamp, context.output_dir)
        ris_file = run_dir / f"academic_dataset_{context.timestamp}.ris"

        ris_file.write_text(renderers.render_ris(context.papers), encoding="utf-8")
        logger.info("RIS Export: %s", ris_file)
