import logging

from academic_hunter.core.writing import renderers

from .base import BaseExporter, ExportContext

logger = logging.getLogger("academic_hunter.exporters")


class BibtexExporter(BaseExporter):
    """The run's bibliography, written into the run directory.

    The text comes from ``renderers.render_bibtex``, which the ``export_report``
    tool also calls — the two used to render it separately and had drifted.
    """

    def export(self, context: ExportContext) -> None:
        run_dir = self._get_run_dir(context.timestamp, context.output_dir)
        bib_file = run_dir / f"academic_dataset_{context.timestamp}.bib"

        bib_file.write_text(renderers.render_bibtex(context.papers), encoding="utf-8")
        logger.info("BibTeX Export: %s", bib_file)
