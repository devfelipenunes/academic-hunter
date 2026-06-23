import logging
from pathlib import Path
from typing import List, Dict, Any
from .base import BaseExporter, ExportContext

logger = logging.getLogger("academic_hunter.exporters")


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
                f.write(f"TI  - {row.get('Title', '')}\n")
                f.write(f"JO  - {row.get('Venue', 'Unknown')}\n")
                year = str(row.get('Year', ''))[:4]
                if year:
                    f.write(f"PY  - {year}\n")
                f.write(f"UR  - {row.get('URL', '')}\n")
                f.write(f"DO  - {row.get('DOI', '')}\n")
                # Abstract is N2
                abstract = str(row.get('Abstract', '')).replace('\n', ' ')
                f.write(f"N2  - {abstract}\n")
                f.write("ER  - \n\n")
        print(f"📄 RIS Export: {ris_file}")
