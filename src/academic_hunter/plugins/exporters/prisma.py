import logging
from pathlib import Path
from typing import List, Dict, Any
from .base import BaseExporter, ExportContext

logger = logging.getLogger("academic_hunter.exporters")


class PrismaExporter(BaseExporter):
    is_prisma = True

    def export(self, context: ExportContext) -> None:
        papers = context.papers
        stats = context.stats
        settings = context.settings
        query_history = context.query_history
        anchors = context.anchors
        tech_strings = context.tech_strings
        timestamp = context.timestamp
        output_dir = context.output_dir

        total_identified = sum(stats.get("identified", {}).values())
        duplicates = stats.get("duplicates_removed", 0)
        excluded_year = stats.get("excluded_year", 0)
        excluded_anchors = stats.get("excluded_anchors", 0)
        excluded_tech = stats.get("excluded_technical_score", 0)
        final = stats.get("included_final", 0)
        
        run_dir = self._get_run_dir(timestamp, output_dir)
        prisma_file = run_dir / f"FLUXO_PRISMA_{timestamp}.md"
        
        sources_mermaid = "\n".join([f"        S{i}[{source}: {count}]:::identification" for i, (source, count) in enumerate(stats.get("identified", {}).items())])
        sources_links = "\n".join([f"        S{i} --> A" for i in range(len(stats.get("identified", {})))])

        mermaid_content = f"""```mermaid
graph TD
    classDef identification fill:#D4E6F1,stroke:#2E86C1,stroke-width:2px;
    classDef screening fill:#FCF3CF,stroke:#F4D03F,stroke-width:2px;
    classDef exclusion fill:#FADBD8,stroke:#E74C3C,stroke-width:2px;
    classDef included fill:#D5F5E3,stroke:#2ECC71,stroke-width:2px,font-weight:bold;

    subgraph Sources
{sources_mermaid}
    end
{sources_links}

    A[Total Records Identified: {total_identified}]:::identification --> B{{Deduplication}}:::screening
    B -->|Duplicates Removed: {duplicates}| C[Duplicate Records Excluded]:::exclusion
    B -->|Unique Records: {total_identified - duplicates}| D{{Temporal Filter}}:::screening
    D -->|Published < {settings.get('start_year', 2021)}: {excluded_year}| E[Excluded: Out of Date Range]:::exclusion
    D -->|Passed: {total_identified - duplicates - excluded_year}| F{{Anchor Screening}}:::screening
    F -->|No Core Anchors: {excluded_anchors}| G[Excluded: Out of Scope]:::exclusion
    F -->|Passed: {total_identified - duplicates - excluded_year - excluded_anchors}| H{{Technical Evaluation}}:::screening
    H -->|Failed Score: {excluded_tech}| I[Excluded: Low Technical Density]:::exclusion
    H -->|Passed: {final}| J[Final Studies Included in Review]:::included
```"""

        config_metadata = f"""## 🔎 Reproducibility Metadata
- **Start Year Filter:** {settings.get('start_year', 2021)}
- **Minimum Relevance Score:** {settings.get('min_relevance_score', 5.0)}
- **Title Multiplier Bonus:** {settings.get('title_multiplier', 1.5)}x
- **Score Precision:** {settings.get('score_precision', 1)} decimal place(s)
- **Grid Anchors:** {list(anchors.keys())}
- **Grid Technical Domains:** {list(tech_strings.keys())}
"""

        exclusion_table = """### 📊 Exclusions by Database Source

| Source | Excluded (Temporal) | Excluded (No Core Anchors) | Excluded (Low Tech Score) | Total Excluded |
| :--- | :---: | :---: | :---: | :---: |
"""
        exclusions_by_src = stats.get("exclusions_by_source", {})
        for src in sorted(stats.get("identified", {}).keys()):
            src_excl = exclusions_by_src.get(src, {"year": 0, "anchor": 0, "score": 0})
            y_excl = src_excl.get("year", 0)
            a_excl = src_excl.get("anchor", 0)
            s_excl = src_excl.get("score", 0)
            tot_excl = y_excl + a_excl + s_excl
            exclusion_table += f"| **{src}** | {y_excl} | {a_excl} | {s_excl} | {tot_excl} |\n"

        query_history_md = "### 📜 Search Queries History\n\n"
        if query_history:
            for item in query_history:
                query_history_md += f"- **{item['Source']}:** `{item['Query']}`\n"
        else:
            query_history_md += "*No queries recorded (mock run or empty search).*\n"

        # Build Consensus & Rigor Statistics Tables
        consensus_counts = {}
        peer_review_counts = {}
        for paper in papers:
            sources_list = [s.strip() for s in paper.get("Source", "").split(",") if s.strip()]
            num_sources = len(sources_list)
            label = f"{num_sources} database" if num_sources == 1 else f"{num_sources} databases"
            consensus_counts[label] = consensus_counts.get(label, 0) + 1
            
            pr = paper.get("Peer_Reviewed", "Unknown")
            peer_review_counts[pr] = peer_review_counts.get(pr, 0) + 1
            
        consensus_table = "### 🔗 Database Consensus Overlap\n\n| Overlap Level | Count of Studies |\n| :--- | :---: |\n"
        sorted_consensus = sorted(consensus_counts.keys(), key=lambda x: int(x.split()[0]))
        for lvl in sorted_consensus:
            consensus_table += f"| {lvl} | {consensus_counts[lvl]} |\n"

        pr_table = "### 🛡️ Peer Review Rigor Distribution\n\n| Rigor / Status | Count of Studies |\n| :--- | :---: |\n"
        for pr, count in sorted(peer_review_counts.items()):
            pr_table += f"| {pr} | {count} |\n"

        with open(prisma_file, 'w', encoding='utf-8') as f:
            f.write(f"# PRISMA Flow Report - {timestamp}\n\n")
            f.write(config_metadata + "\n")
            f.write("## 1. Breakdown by Source\n")
            for source, count in stats.get("identified", {}).items():
                f.write(f"- **{source}:** {count}\n")
            f.write(f"\n- **Total Identified:** {total_identified}\n")
            f.write(f"- **Duplicates Removed:** {duplicates}\n")
            f.write(f"- **Excluded (Publication Year < {settings.get('start_year', 2021)}):** {excluded_year}\n")
            f.write(f"- **Excluded (No Industry Anchors):** {excluded_anchors}\n")
            f.write(f"- **Excluded (Low Relevance Score):** {excluded_tech}\n")
            f.write(f"- **Final Included:** {final}\n\n")
            
            f.write(exclusion_table + "\n")
            
            f.write("## 2. Visual Flow (Mermaid)\n\n")
            f.write(mermaid_content + "\n\n")
            
            f.write("## 3. Consensus & Rigor Statistics\n\n")
            f.write(consensus_table + "\n")
            f.write(pr_table + "\n")
            
            f.write("## 4. Query Execution History\n\n")
            f.write(query_history_md + "\n")

        print(f"📊 PRISMA Report: {prisma_file}")
