import logging
from pathlib import Path
from typing import List, Dict, Any
from .base import BaseExporter, ExportContext

logger = logging.getLogger("academic_hunter.exporters")


def one_line(value: Any) -> str:
    """Collapse a value onto one line: RIS is line-oriented, and a newline in a
    value ends the field and turns the rest into a tag the reader cannot place."""
    return " ".join(str(value if value is not None else "").split())


class RisExporter(BaseExporter):
    def export(self, context: ExportContext) -> None:
        papers = context.papers
        timestamp = context.timestamp
        output_dir = context.output_dir

        if not papers:
            return
            
        run_dir = self._get_run_dir(timestamp, output_dir)
        ris_file = run_dir / f"academic_dataset_{timestamp}.ris"
        
        with open(ris_file, 'w', encoding='utf-8') as f:
            for row in papers:
                f.write("TY  - JOUR\n")
                f.write(f"TI  - {one_line(row.get('Title', ''))}\n")
                f.write(f"JO  - {one_line(row.get('Venue', 'Unknown'))}\n")
                year = str(row.get('Year', ''))[:4]
                if year:
                    f.write(f"PY  - {year}\n")
                f.write(f"UR  - {one_line(row.get('URL', ''))}\n")
                f.write(f"DO  - {one_line(row.get('DOI', ''))}\n")
                f.write(f"N2  - {one_line(row.get('Abstract', ''))}\n")
                f.write("ER  - \n\n")
        logger.info("RIS Export: %s", ris_file)
