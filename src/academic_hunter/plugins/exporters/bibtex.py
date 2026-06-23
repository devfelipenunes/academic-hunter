import logging
from pathlib import Path
from typing import List, Dict, Any
from .base import BaseExporter, ExportContext

logger = logging.getLogger("academic_hunter.exporters")


class BibtexExporter(BaseExporter):
    def export(self, context: ExportContext) -> None:
        papers = context.papers
        timestamp = context.timestamp
        output_dir = context.output_dir

        if not papers:
            return
            
        run_dir = self._get_run_dir(timestamp, output_dir)
        bib_file = run_dir / f"academic_dataset_{timestamp}.bib"
        
        with open(bib_file, 'w', encoding='utf-8') as f:
            for index, row in enumerate(papers):
                title = row.get('Title', '')
                clean_title = "".join(c for c in title if c.isalnum())[:15].lower()
                year = str(row.get('Year', ''))[:4] or "2021"
                cite_key = f"{clean_title}_{year}_{index}"
                
                f.write(f"@article{{{cite_key},\n")
                f.write(f"  title = {{{title}}},\n")
                f.write(f"  journal = {{{row.get('Venue', 'Unknown')}}},\n")
                f.write(f"  year = {{{year}}},\n")
                f.write(f"  url = {{{row.get('URL', '')}}},\n")
                f.write(f"  doi = {{{row.get('DOI', '')}}},\n")
                # Clean up abstract text for bibtex
                abstract = str(row.get('Abstract', '')).replace('{', '\\{').replace('}', '\\}')
                f.write(f"  abstract = {{{abstract}}}\n")
                f.write("}\n\n")
        print(f"📄 BibTeX Export: {bib_file}")
