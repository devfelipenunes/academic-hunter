import logging
from typing import Any, Dict

from academic_hunter.core.infra.atomic import write_json_atomically
from academic_hunter.core.models.citations import citation_summary
from academic_hunter.core.models.utils import abstract_summary

from .base import BaseExporter, ExportContext

logger = logging.getLogger("academic_hunter.exporters")


def _citation_weight(settings: Dict[str, Any]) -> Any:
    """The citation weight in force, defaulted the way the fusion defaults it."""
    weights = settings.get("fusion_weights")
    if not isinstance(weights, dict):
        return 0.0
    return weights.get("citation", 0.0)


def flow_counts(stats: Dict[str, Any]) -> Dict[str, Any]:
    """Every count the PRISMA flow reports, and whether it reconciles.

    Technical Evaluation is where the two families of counters meet: everything
    the earlier filters passed is split into the excluded and the included that
    the ranking step writes. `closes` is that identity, and it is reported rather
    than enforced — a diagram that silently balanced would hide a real
    disagreement instead of showing it.
    """
    total_identified = sum(stats.get("identified", {}).values())
    duplicates = stats.get("duplicates_removed", 0)
    excluded_year = stats.get("excluded_year", 0)
    excluded_anchors = stats.get("excluded_anchors", 0)
    excluded_tech = stats.get("excluded_technical_score", 0)
    final = stats.get("included_final", 0)

    unique = total_identified - duplicates
    after_year = unique - excluded_year
    evaluated = after_year - excluded_anchors

    return {
        "total_identified": total_identified,
        "duplicates": duplicates,
        "excluded_year": excluded_year,
        "excluded_anchors": excluded_anchors,
        "excluded_tech": excluded_tech,
        "final": final,
        "unique": unique,
        "after_year": after_year,
        "evaluated": evaluated,
        "closes": evaluated == excluded_tech + final,
    }


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

        counts = flow_counts(stats)
        total_identified = counts["total_identified"]
        duplicates = counts["duplicates"]
        excluded_year = counts["excluded_year"]
        excluded_anchors = counts["excluded_anchors"]
        excluded_tech = counts["excluded_tech"]
        final = counts["final"]
        unique = counts["unique"]
        after_year = counts["after_year"]
        evaluated = counts["evaluated"]

        if not counts["closes"]:
            logger.warning(
                "PRISMA flow does not close at Technical Evaluation: %d entered, "
                "but %d excluded + %d included = %d. The diagram reports the "
                "numbers as recorded; treat this run's stats as suspect.",
                evaluated, excluded_tech, final, excluded_tech + final,
            )

        run_dir = self._get_run_dir(timestamp, output_dir)
        prisma_file = run_dir / f"FLUXO_PRISMA_{timestamp}.md"

        stats_file = run_dir / f"run_stats_{timestamp}.json"
        write_json_atomically(stats_file, {
            "timestamp": timestamp,
            "identified": stats.get("identified", {}),
            "duplicates_removed": duplicates,
            "excluded_year": excluded_year,
            "excluded_anchors": excluded_anchors,
            "excluded_technical_score": excluded_tech,
            "included_final": final,
            "inclusion_predicate": stats.get("inclusion_predicate"),
            "score_distribution": stats.get("score_distribution"),
            "abstracts": abstract_summary(papers),
            "full_text": stats.get("full_text", {}),
            "exclusions_by_source": stats.get("exclusions_by_source", {}),
            "unavailable_sources": stats.get("unavailable_sources", {}),
            "blocked_sources": stats.get("blocked_sources", []),
            "settings": {
                "start_year": settings.get("start_year"),
                "min_relevance_score": settings.get("min_relevance_score"),
                "min_inclusion_score": settings.get("min_inclusion_score"),
                "limit_per_query": settings.get("limit_per_query"),
                "ranking_query": settings.get("ranking_query", ""),
                "title_multiplier": settings.get("title_multiplier", 1.5),
            },
            "anchors": sorted(anchors) if isinstance(anchors, dict) else anchors,
            "technical_domains": (
                sorted(tech_strings) if isinstance(tech_strings, dict) else tech_strings
            ),
            "configuration": context.run_config,
        })

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
    B -->|Unique Records: {unique}| D{{Temporal Filter}}:::screening
    D -->|Published < {settings.get('start_year', 2021)}: {excluded_year}| E[Excluded: Out of Date Range]:::exclusion
    D -->|Passed: {after_year}| F{{Anchor Screening}}:::screening
    F -->|No Core Anchors: {excluded_anchors}| G[Excluded: Out of Scope]:::exclusion
    F -->|Passed: {evaluated}| H{{Technical Evaluation}}:::screening
    H -->|Failed Score: {excluded_tech}| I[Excluded: Low Technical Density]:::exclusion
    H -->|Passed: {final}| J[Final Studies Included in Review]:::included
```"""

        predicate = stats.get("inclusion_predicate")
        closure = (
            f"{evaluated} evaluated = {excluded_tech} excluded + {final} included"
            + ("" if counts["closes"] else "  ⚠️ does not reconcile")
        )

        coverage = citation_summary(papers)
        backfill = stats.get("citation_backfill") or {}
        impact = stats.get("impact") or {}
        citation_block = (
            f"- **Citations Recorded:** {coverage['with_count']} of {coverage['papers']} "
            f"({coverage['reported']} reported by their source, "
            f"{coverage['resolved']} filled in by a lookup)\n"
            f"- **Citations Not Recorded:** {coverage['confirmed_zero']} confirmed zero by a "
            f"source, {coverage['unresolved']} unresolved, "
            f"{coverage['without_identifier']} with no identifier to ask about, "
            f"{coverage['not_asked']} never asked\n"
        )
        if backfill:
            citation_block += (
                f"- **Citation Backfill:** {backfill.get('papers_recovered', 0)} counts "
                f"recovered over {backfill.get('requests', 0)} batched request(s) for "
                f"{backfill.get('papers_asked', 0)} papers\n"
            )
        citation_block += (
            f"- **Citation Weight:** {_citation_weight(settings)} "
            "(0 means citations do not affect `Relevance_Score`)\n"
        )
        if impact:
            citation_block += (
                f"- **Impact Band:** {impact.get('cutoff', 0):g}+ citations, the "
                f"{impact.get('percentile')}th percentile of this run's "
                f"{impact.get('papers_measured', 0)} measured papers\n"
            )

        abstracts = abstract_summary(papers)
        abstract_block = (
            f"- **Abstracts Recorded:** {abstracts['with_abstract']} of "
            f"{abstracts['papers']}\n"
        )
        if abstracts["without_abstract"]:
            abstract_block += (
                f"- **Abstracts Not Recorded:** {abstracts['without_abstract']} — the "
                "anchor gate and the term tally read those papers through their "
                "titles alone, and their titles carry no multiplier; "
                + ", ".join(f"*{t}*" for t in abstracts["without_abstract_titles"][:10])
                + "\n"
            )

        published = stats.get("published_version") or {}
        published_block = ""
        if published:
            confirmed = published.get("promoted", 0) - published.get("promoted_on_title_alone", 0)
            published_block = (
                f"- **Preprints Examined:** {published.get('asked', 0)} of "
                f"{published.get('preprints', 0)} — "
                f"{published.get('without_identifier', 0)} without an identifier to "
                f"be the preprint of\n"
                f"- **Published Versions Found:** {published.get('promoted', 0)} — "
                f"{confirmed} confirmed by a shared author, "
                f"{published.get('promoted_on_title_alone', 0)} on the title alone; "
                f"{published.get('unmatched', 0)} left as they were\n"
            )
            for entry in (published.get("promotions") or [])[:10]:
                published_block += (
                    f"  - *{entry.get('title', '')}* → {entry.get('venue') or 'unnamed venue'}"
                    f" ({entry.get('year') or 'year unknown'}), `{entry.get('published_doi', '')}`\n"
                )
            published_block += (
                "\nA preprint is recorded as `Likely` published, never as `Yes`: a "
                "matching record is evidence that a published version exists, and "
                "not evidence that anyone reviewed it. A paper with no match keeps "
                "the venue and year it arrived with. The published DOI is reported "
                "here and not written into `DOI`, which is this run's identity for "
                "the paper.\n"
            )

        config_metadata = f"""## 🔎 Reproducibility Metadata
- **Start Year Filter:** {settings.get('start_year', 2021)}
- **Inclusion Predicate:** `{predicate}`{"" if predicate else " (not recorded by this run)"}
- **Technical Evaluation:** {closure}
- **Title Multiplier Bonus:** {settings.get('title_multiplier', 1.5)}x
- **Score Precision:** {settings.get('score_precision', 1)} decimal place(s)
- **Ranking Query:** {settings.get('ranking_query') or "*(none — the run was ordered by the term tally)*"}
- **Grid Anchors:** {list(anchors.keys())}
- **Grid Technical Domains:** {list(tech_strings.keys())}
{citation_block}{abstract_block}{published_block}
The inclusion predicate is the criterion, stated as applied: a paper is in the
review when its own weighted tally of the configured domain terms reaches the
threshold. It is a property of the paper, so the same paper is included by two
runs of the same configuration. `Relevance_Score` is the run's ordering and is
reported separately in the results table; it is not the inclusion criterion.

A citation count is listed with the source accountable for it. A `0` recorded as
confirmed by a source and a `0` no source could answer for are different facts,
and only the first is a measurement.

The title multiplier is applied only to papers that carry an abstract. A record
with nothing but a title has no abstract the gate could screen and no abstract
terms to balance the title's, so boosting the title would rank it above papers
that were read in full.
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
            f.write(f"- **Excluded (Below the Inclusion Predicate):** {excluded_tech}\n")
            f.write(f"- **Final Included:** {final}\n\n")

            full_text = stats.get("full_text") or {}
            if full_text:
                f.write("### Full Text Retrieval\n\n")
                f.write(f"- **Obtained:** {full_text.get('obtained', 0)}\n")
                if full_text.get("already_indexed"):
                    f.write(
                        "- **Already indexed (not re-fetched):** "
                        f"{full_text['already_indexed']}\n"
                    )
                for status, count in sorted(full_text.items()):
                    if status in ("obtained", "already_indexed") or not count:
                        continue
                    f.write(f"- **Not obtained — {status}:** {count}\n")
                f.write("\n")

            f.write(exclusion_table + "\n")
            
            f.write("## 2. Visual Flow (Mermaid)\n\n")
            f.write(mermaid_content + "\n\n")
            
            f.write("## 3. Consensus & Rigor Statistics\n\n")
            f.write(consensus_table + "\n")
            f.write(pr_table + "\n")
            
            f.write("## 4. Query Execution History\n\n")
            f.write(query_history_md + "\n")

        logger.info("PRISMA Report: %s", prisma_file)
