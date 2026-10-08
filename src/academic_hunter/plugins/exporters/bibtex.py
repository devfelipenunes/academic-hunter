import logging

from academic_hunter.core.models.utils import (
    bibtex_authors,
    escape_bibtex,
    paper_order_key,
)
from academic_hunter.core.writing.style import paper_citation_key

from .base import BaseExporter, ExportContext

logger = logging.getLogger("academic_hunter.exporters")


class BibtexExporter(BaseExporter):
    def export(self, context: ExportContext) -> None:
        papers = context.papers
        timestamp = context.timestamp
        output_dir = context.output_dir

        run_dir = self._get_run_dir(timestamp, output_dir)
        bib_file = run_dir / f"academic_dataset_{timestamp}.bib"

        with open(bib_file, 'w', encoding='utf-8') as f:
            for row in sorted(papers, key=paper_order_key):
                title = row.get('Title', '')
                year = str(row.get('Year', ''))[:4] or "2021"
                cite_key = paper_citation_key(row)

                f.write(f"@article{{{cite_key},\n")
                f.write(f"  title = {{{escape_bibtex(title)}}},\n")
                authors = bibtex_authors(row.get('Authors', ''))
                if authors:
                    f.write(f"  author = {{{escape_bibtex(authors)}}},\n")
                f.write(f"  journal = {{{escape_bibtex(row.get('Venue', 'Unknown'))}}},\n")
                f.write(f"  year = {{{year}}},\n")
                f.write(f"  url = {{{escape_bibtex(row.get('URL', ''))}}},\n")
                f.write(f"  doi = {{{escape_bibtex(row.get('DOI', ''))}}},\n")
                f.write(f"  abstract = {{{escape_bibtex(row.get('Abstract', ''))}}}\n")
                f.write("}\n\n")
        logger.info("BibTeX Export: %s", bib_file)
