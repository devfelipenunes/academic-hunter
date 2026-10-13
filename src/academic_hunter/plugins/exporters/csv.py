import logging

import pandas as pd

from academic_hunter.core.models.schema import FIELD_SCHEMA
from academic_hunter.core.models.utils import (
    neutralise_formula,
    paper_order_key,
    strip_abstract_placeholder,
)

from .base import BaseExporter, ExportContext

logger = logging.getLogger("academic_hunter.exporters")


class CsvExporter(BaseExporter):
    """The dataset, one row per study.

    Two columns are derived rather than copied — ``Database_Count`` from
    ``Source``, and the row order from ``paper_order_key``. The schema knows what
    every field defaults to, and filling from it is what keeps one partially
    normalised paper from taking the whole dataset with it.

    The rows are ordered before the frame is built rather than sorted afterwards:
    ``DataFrame.sort_values`` defaults to an unstable quicksort, so the relative
    order of papers sharing a ``Relevance_Score`` was undefined — and it stayed
    undefined even with a stable sort, because the order the papers arrive in is
    itself a product of concurrent mining. 287 of the 310 papers of the last run
    sat inside a tie, which is why two runs of one corpus disagreed on 214 rows.

    Both paths write the same header. The empty one used to put
    ``Database_Count`` first and the populated one put it last, so a reader that
    takes columns by position read a different dataset depending on whether the
    run qualified anything.

    ``Has_Abstract`` is derived for the same reason ``Database_Count`` is: a row
    whose abstract cell is empty is a row the anchor gate and the term tally could
    only read through its title, and no column said so.
    """

    DERIVED_COLUMNS = ("Database_Count", "Has_Abstract")

    def export(self, context: ExportContext) -> None:
        papers = context.papers
        timestamp = context.timestamp
        output_dir = context.output_dir

        run_dir = self._get_run_dir(timestamp, output_dir)
        csv_file = run_dir / f"academic_dataset_{timestamp}.csv"

        if not papers:
            pd.DataFrame(columns=[*FIELD_SCHEMA, *self.DERIVED_COLUMNS]).to_csv(
                csv_file, index=False, encoding="utf-8"
            )
            logger.info("No studies qualified; empty dataset: %s", csv_file)
            return

        def get_db_count(source_str):
            if not source_str: return 1
            return len([s.strip() for s in source_str.split(',') if s.strip()])

        df = pd.DataFrame(sorted(papers, key=paper_order_key))
        for field, spec in FIELD_SCHEMA.items():
            if field not in df.columns:
                df[field] = spec["default"]
        df['Database_Count'] = df['Source'].apply(get_db_count)
        df['Has_Abstract'] = df['Abstract'].apply(
            lambda value: bool(strip_abstract_placeholder(value).strip())
        )

        for column in df.columns:
            df[column] = df[column].map(neutralise_formula)

        df.to_csv(csv_file, index=False, encoding='utf-8')
        logger.info("Dataset: %s", csv_file)

