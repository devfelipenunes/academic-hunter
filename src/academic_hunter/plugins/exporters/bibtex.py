import logging
from typing import Any

from academic_hunter.core.writing.style import BibtexKeyAllocator

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

        run_dir = self._get_run_dir(timestamp, output_dir)
        bib_file = run_dir / f"academic_dataset_{timestamp}.bib"

        # No early return on an empty list: the file is still written, empty, so
        # the run leaves its own artifact instead of an older run's — or the
        # unfiltered one written before the threshold was applied.
        allocate_key = BibtexKeyAllocator()

        with open(bib_file, 'w', encoding='utf-8') as f:
            for row in papers:
                title = row.get('Title', '')
                year = str(row.get('Year', ''))[:4] or "2021"
                cite_key = allocate_key(title, year)

                f.write(f"@article{{{cite_key},\n")
                f.write(f"  title = {{{escape_bibtex(title)}}},\n")
                f.write(f"  journal = {{{escape_bibtex(row.get('Venue', 'Unknown'))}}},\n")
                f.write(f"  year = {{{year}}},\n")
                f.write(f"  url = {{{escape_bibtex(row.get('URL', ''))}}},\n")
                f.write(f"  doi = {{{escape_bibtex(row.get('DOI', ''))}}},\n")
                f.write(f"  abstract = {{{escape_bibtex(row.get('Abstract', ''))}}}\n")
                f.write("}\n\n")
        logger.info("BibTeX Export: %s", bib_file)
