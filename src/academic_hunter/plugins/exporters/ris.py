import logging

from academic_hunter.core.models.authors import split_authors
from academic_hunter.core.models.utils import one_line, paper_order_key

from .base import BaseExporter, ExportContext

logger = logging.getLogger("academic_hunter.exporters")


class RisExporter(BaseExporter):
    def export(self, context: ExportContext) -> None:
        papers = context.papers
        timestamp = context.timestamp
        output_dir = context.output_dir

        run_dir = self._get_run_dir(timestamp, output_dir)
        ris_file = run_dir / f"academic_dataset_{timestamp}.ris"

        with open(ris_file, 'w', encoding='utf-8') as f:
            for row in sorted(papers, key=paper_order_key):
                f.write("TY  - JOUR\n")
                f.write(f"TI  - {one_line(row.get('Title', ''))}\n")
                for author in split_authors(row.get('Authors', '')):
                    f.write(f"AU  - {one_line(author)}\n")
                f.write(f"JO  - {one_line(row.get('Venue', 'Unknown'))}\n")
                year = str(row.get('Year', ''))[:4]
                if year:
                    f.write(f"PY  - {year}\n")
                f.write(f"UR  - {one_line(row.get('URL', ''))}\n")
                f.write(f"DO  - {one_line(row.get('DOI', ''))}\n")
                f.write(f"N2  - {one_line(row.get('Abstract', ''))}\n")
                f.write("ER  - \n\n")
        logger.info("RIS Export: %s", ris_file)
