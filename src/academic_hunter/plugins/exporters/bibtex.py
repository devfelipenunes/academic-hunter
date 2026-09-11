import logging
from pathlib import Path
from typing import List, Dict, Any
from .base import BaseExporter, ExportContext

logger = logging.getLogger("academic_hunter.exporters")

#: Single pass, so the backslashes this inserts are not themselves escaped.
_BIBTEX_ESCAPES = str.maketrans({
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
})


def escape_bibtex(value: Any) -> str:
    """Escape what would end a field early: a `}` in a title closes the record."""
    return str(value if value is not None else "").translate(_BIBTEX_ESCAPES)


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
                f.write(f"  title = {{{escape_bibtex(title)}}},\n")
                f.write(f"  journal = {{{escape_bibtex(row.get('Venue', 'Unknown'))}}},\n")
                f.write(f"  year = {{{year}}},\n")
                f.write(f"  url = {{{escape_bibtex(row.get('URL', ''))}}},\n")
                f.write(f"  doi = {{{escape_bibtex(row.get('DOI', ''))}}},\n")
                f.write(f"  abstract = {{{escape_bibtex(row.get('Abstract', ''))}}}\n")
                f.write("}\n\n")
        logger.info("BibTeX Export: %s", bib_file)
