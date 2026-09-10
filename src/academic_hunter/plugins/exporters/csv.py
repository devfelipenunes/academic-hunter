import logging
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any
from .base import BaseExporter, ExportContext

logger = logging.getLogger("academic_hunter.exporters")

_FORMULA_PREFIXES = ("=", "+", "-", "@")


def _neutralise(value: Any) -> Any:
    """Defuse a cell a spreadsheet would evaluate as a formula.

    A title or abstract starting with ``=``, ``+``, ``-`` or ``@`` runs as a
    formula when the file is opened in Excel or LibreOffice. These fields come
    from third-party APIs, so the content is not ours to trust.
    """
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


class CsvExporter(BaseExporter):
    def export(self, context: ExportContext) -> None:
        papers = context.papers
        timestamp = context.timestamp
        output_dir = context.output_dir

        if not papers:
            logger.info("No studies to export to CSV.")
            return
            
        def get_db_count(source_str):
            if not source_str: return 1
            return len([s.strip() for s in source_str.split(',') if s.strip()])
            
        df = pd.DataFrame(papers)
        df['Database_Count'] = df['Source'].apply(get_db_count)

        for column in df.columns:
            df[column] = df[column].map(_neutralise)

        df = df.sort_values(by='Relevance_Score', ascending=False)
        
        run_dir = self._get_run_dir(timestamp, output_dir)
        csv_file = run_dir / f"academic_dataset_{timestamp}.csv"
        df.to_csv(csv_file, index=False, encoding='utf-8')
        logger.info("Dataset: %s", csv_file)

