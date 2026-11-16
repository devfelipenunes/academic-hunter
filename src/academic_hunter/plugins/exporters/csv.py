import logging

from academic_hunter.core.writing import renderers

from .base import BaseExporter, ExportContext

logger = logging.getLogger("academic_hunter.exporters")


class CsvExporter(BaseExporter):
    """The dataset, one row per study, written into the run directory.

    The text comes from ``renderers.render_csv``, which is also where the column
    set, the row order and the two derived columns are decided — and where the
    ``export_report`` tool gets its CSV from, so the two cannot disagree.
    """

    def export(self, context: ExportContext) -> None:
        run_dir = self._get_run_dir(context.timestamp, context.output_dir)
        csv_file = run_dir / f"academic_dataset_{context.timestamp}.csv"

        csv_file.write_text(renderers.render_csv(context.papers), encoding="utf-8")
        if context.papers:
            logger.info("Dataset: %s", csv_file)
        else:
            logger.info("No studies qualified; empty dataset: %s", csv_file)
