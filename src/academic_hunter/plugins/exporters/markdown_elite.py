import logging
from pathlib import Path
from typing import List, Dict, Any
from .base import BaseExporter, ExportContext

logger = logging.getLogger("academic_hunter.exporters")


class MarkdownEliteExporter(BaseExporter):
    def export(self, context: ExportContext) -> None:
        papers = context.papers
        stats = context.stats
        timestamp = context.timestamp
        output_dir = context.output_dir

        run_dir = self._get_run_dir(timestamp, output_dir)
        report_file = run_dir / f"RELATORIO_ELITE_{timestamp}.md"
        
        sorted_papers = sorted(papers, key=lambda x: x.get("Relevance_Score", 0.0), reverse=True)
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(f"# Academic Hunter Elite Report - {timestamp}\n\n")
            for row in sorted_papers:
                f.write(f"### {row.get('Title')} (Score: {row.get('Relevance_Score')})\n")
                f.write(f"- **Year:** {row.get('Year')} | **Citations:** {row.get('Citations')}\n")
                f.write(f"- **Venue:** {row.get('Venue')} | **Peer-Reviewed:** {row.get('Peer_Reviewed')}\n")
                f.write(f"- **Source:** {row.get('Source')} | **DOI:** {row.get('DOI')}\n")
                f.write(f"- **Anchors:** {row.get('Anchor_Category')}\n")
                f.write(f"- [Link]({row.get('URL')})\n\n")
            
            f.write("## PRISMA Flow Stats\n")
            f.write(f"- **Identified:** {stats.get('identified')}\n")
            f.write(f"- **Duplicates Removed:** {stats.get('duplicates_removed')}\n")
            f.write(f"- **Excluded (Publication Year):** {stats.get('excluded_year', 0)}\n")
            f.write(f"- **Excluded (No Industry Anchors):** {stats.get('excluded_anchors', 0)}\n")
            f.write(f"- **Excluded (Low Relevance Score):** {stats.get('excluded_technical_score', 0)}\n")
            f.write(f"- **Final Included:** {stats.get('included_final')}\n")
            
        print(f"📝 Master Report: {report_file}")
