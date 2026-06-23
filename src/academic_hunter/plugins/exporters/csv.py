import logging
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any
from .base import BaseExporter, ExportContext


class CsvExporter(BaseExporter):
    def export(self, context: ExportContext) -> None:
        papers = context.papers
        timestamp = context.timestamp
        output_dir = context.output_dir

        if not papers:
            print("⚠️ No studies to export to CSV.")
            return
            
        def get_db_count(source_str):
            if not source_str: return 1
            return len([s.strip() for s in source_str.split(',') if s.strip()])
            
        df = pd.DataFrame(papers)
        df['Database_Count'] = df['Source'].apply(get_db_count)
        
        # Sort by Relevance Score desc
        df = df.sort_values(by='Relevance_Score', ascending=False)
        
        run_dir = self._get_run_dir(timestamp, output_dir)
        csv_file = run_dir / f"academic_dataset_{timestamp}.csv"
        df.to_csv(csv_file, index=False, encoding='utf-8')
        print(f"📊 Dataset: {csv_file}")

