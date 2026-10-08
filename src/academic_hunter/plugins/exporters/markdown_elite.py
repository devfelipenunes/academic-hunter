import logging

from ...core.models.citations import citation_summary, citation_tokens
from ...core.models.utils import paper_order_key
from .base import BaseExporter, ExportContext

logger = logging.getLogger("academic_hunter.exporters")


def _provenance(citations, source) -> str:
    """How the citation count was obtained, in the reader's words.

    A count with no provenance would let a paper no source could answer for look
    identical to one every source agreed was never cited.
    """
    tokens = citation_tokens(source)
    try:
        count = int(citations or 0)
    except (TypeError, ValueError):
        count = 0
    if not tokens:
        return "no source asked"
    if count:
        return f"counted by {', '.join(sorted(tokens))}"
    if "none" in tokens:
        return "no source can answer"
    if "unresolved" in tokens:
        return "no source answered"
    return f"reported zero by {', '.join(sorted(tokens))}"


class MarkdownEliteExporter(BaseExporter):
    def export(self, context: ExportContext) -> None:
        papers = context.papers
        stats = context.stats
        timestamp = context.timestamp
        output_dir = context.output_dir

        run_dir = self._get_run_dir(timestamp, output_dir)
        report_file = run_dir / f"RELATORIO_ELITE_{timestamp}.md"

        sorted_papers = sorted(papers, key=paper_order_key)

        predicate = stats.get("inclusion_predicate")
        distribution = stats.get("score_distribution") or {}
        admitted = distribution.get("n")
        coverage = citation_summary(sorted_papers)
        impact = stats.get("impact") or {}

        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(f"# Academic Hunter Elite Report - {timestamp}\n\n")
            f.write("## How Inclusion Was Decided\n\n")
            f.write(
                f"- **Predicate:** `{predicate}`"
                f"{'' if predicate else ' (not recorded by this run)'}\n"
            )
            f.write(
                f"- **Admitted:** {stats.get('included_final', len(sorted_papers))}"
                + (f" of {admitted} evaluated\n" if admitted else "\n")
            )
            f.write(
                "- **Listed by:** `Relevance_Score`, which orders *this run* against "
                "its own range and is not the inclusion criterion. `_kw_score` is "
                "the paper's own weighted tally of the configured domain terms, "
                "and is what the predicate reads.\n"
            )
            f.write(
                f"- **Citations:** {coverage['with_count']} of {coverage['papers']} "
                f"papers carry a count — {coverage['reported']} reported by their "
                f"source, {coverage['resolved']} filled in by a lookup. "
                f"{coverage['confirmed_zero']} were confirmed zero by a source, "
                f"{coverage['unresolved']} could not be resolved, "
                f"{coverage['without_identifier']} carry no identifier to ask about"
                + (
                    f", and {coverage['not_asked']} were never asked.\n"
                    if coverage['not_asked']
                    else ".\n"
                )
            )
            f.write(
                "- A `0` is therefore not the same statement as a low number: only "
                "the papers in the first two groups have been measured at all.\n\n"
            )

            for row in sorted_papers:
                f.write(
                    f"### {row.get('Title')} (Relevance_Score: {row.get('Relevance_Score')}"
                    f" | term score: {row.get('_kw_score')})\n"
                )
                f.write(
                    f"- **Year:** {row.get('Year')} | **Citations:** {row.get('Citations')}"
                    f" ({_provenance(row.get('Citations'), row.get('Citations_Source'))})\n"
                )
                if row.get('Authors'):
                    f.write(f"- **Authors:** {row.get('Authors')}\n")
                f.write(f"- **Venue:** {row.get('Venue')} | **Peer-Reviewed:** {row.get('Peer_Reviewed')}\n")
                f.write(f"- **Source:** {row.get('Source')} | **DOI:** {row.get('DOI')}\n")
                f.write(f"- **Anchors:** {row.get('Anchor_Category')}\n")
                f.write(f"- [Link]({row.get('URL')})\n\n")

            self._write_impact_section(f, sorted_papers, coverage, impact)

            f.write("## PRISMA Flow Stats\n")
            f.write(f"- **Identified:** {stats.get('identified')}\n")
            f.write(f"- **Duplicates Removed:** {stats.get('duplicates_removed')}\n")
            f.write(f"- **Excluded (Publication Year):** {stats.get('excluded_year', 0)}\n")
            f.write(f"- **Excluded (No Industry Anchors):** {stats.get('excluded_anchors', 0)}\n")
            f.write(f"- **Excluded (Below the Inclusion Predicate):** {stats.get('excluded_technical_score', 0)}\n")
            f.write(f"- **Final Included:** {stats.get('included_final')}\n")
            
        logger.info("Master Report: %s", report_file)

    def _write_impact_section(self, f, sorted_papers, coverage, impact) -> None:
        """The most-cited papers of the run, next to where the ordering put them.

        It exists to make a disagreement visible rather than to flatter a paper:
        the run's most-cited work has repeatedly sat at the bottom of
        ``Relevance_Score``, and the two columns side by side say so without
        anyone having to recompute it.
        """
        cutoff = float(impact.get("cutoff") or 0.0)
        above = [
            p for p in sorted_papers
            if cutoff > 0 and float(p.get("Citations") or 0) >= cutoff
        ]
        above.sort(key=lambda p: paper_order_key(p, "Citations"))

        f.write("## Most Impactful Works\n\n")
        if not above:
            f.write(
                "No source reported a citation count for this run, so no paper can "
                "be ranked by impact. That is a statement about the data, not "
                "about the corpus.\n\n"
            )
            return

        percentile = impact.get("percentile")
        try:
            percentile_text = f"{float(percentile):g}"
        except (TypeError, ValueError):
            percentile_text = str(percentile)
        f.write(
            f"Papers at or above {cutoff:g} citations, which is where the "
            f"{percentile_text}th percentile of this run's {impact.get('papers_measured', 0)} "
            f"measured papers falls. The line is derived from the run's own "
            f"distribution and not fixed in advance.\n\n"
        )
        f.write("| # | Title | Year | Citations | Counted by | Relevance_Score |\n")
        f.write("| ---: | :--- | ---: | ---: | :--- | ---: |\n")
        for position, paper in enumerate(above, start=1):
            title = str(paper.get("Title") or "").replace("|", "\\|")
            f.write(
                f"| {position} | {title} | {paper.get('Year')} "
                f"| {paper.get('Citations')} "
                f"| {_provenance(paper.get('Citations'), paper.get('Citations_Source'))} "
                f"| {paper.get('Relevance_Score')} |\n"
            )
        f.write("\n")
        if coverage.get("not_asked") or coverage.get("unresolved") or coverage.get("without_identifier"):
            f.write(
                f"{coverage['not_asked'] + coverage['unresolved'] + coverage['without_identifier']} "
                "papers of this run carry no usable count, so the line above is "
                "drawn from the measured ones only.\n\n"
            )
