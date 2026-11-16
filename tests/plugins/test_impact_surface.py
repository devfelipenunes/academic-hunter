"""The two surfaces that show a citation count say where it came from.

Filling in a false zero without saying so would swap one invisible lie for
another. The report's own rule is that a stated number carries its source, and
that a count no source could answer for stops looking like a measured zero.
"""

from pathlib import Path

import pytest

from academic_hunter.plugins.exporters.base import ExportContext
from academic_hunter.plugins.exporters.markdown_elite import MarkdownEliteExporter
from academic_hunter.plugins.exporters.prisma import PrismaExporter


def paper(title, citations, source="", score=5.0, year=2024):
    return {
        "Title": title,
        "Citations": citations,
        "Citations_Source": source,
        "Relevance_Score": score,
        "Year": year,
        "Venue": "A Venue",
        "Peer_Reviewed": True,
        "Source": "OpenAlex",
        "DOI": f"10.1/{title.lower().replace(' ', '-')}",
        "Anchor_Category": "Blockchain",
        "URL": "https://example.org/a",
    }


def context(tmp_path, papers, stats=None, settings=None):
    return ExportContext(
        papers=papers,
        stats={
            "identified": {"openalex": len(papers)},
            "exclusions_by_source": {},
            "included_final": len(papers),
            **(stats or {}),
        },
        settings=settings or {"start_year": 2021, "min_relevance_score": 3.5},
        query_history=[],
        anchors={"Blockchain": ["blockchain"]},
        tech_strings={"Core": ["ledger"]},
        timestamp="test_impact",
        output_dir=tmp_path,
    )


def report(tmp_path, exporter, papers, **kwargs):
    exporter.export(context(tmp_path, papers, **kwargs))
    files = list(Path(tmp_path).rglob("*.md"))
    return files[0].read_text(encoding="utf-8")


IMPACT_STATS = {"impact": {"cutoff": 50.0, "percentile": 90.0, "papers_measured": 4}}


def test_the_per_paper_line_names_the_source_of_the_count(tmp_path):
    """``**Citations:** 75`` alone never said whether anyone had asked."""
    papers = [
        paper("Counted here", 75, "openalex"),
        paper("Filled in later", 120, "openalex-batch"),
        paper("Nobody can answer", 0, "none"),
        paper("Asked and unanswered", 0, "unresolved"),
    ]

    content = report(tmp_path, MarkdownEliteExporter(), papers)

    assert "**Citations:** 75 (counted by openalex)" in content
    assert "**Citations:** 120 (counted by openalex-batch)" in content


def test_an_unanswerable_zero_does_not_read_like_a_measured_one(tmp_path):
    """The whole point of the provenance: these two rows showed the same ``0``."""
    papers = [
        paper("No source exists", 0, "none"),
        paper("Source said zero", 0, "crossref"),
        paper("Source did not answer", 0, "unresolved"),
    ]

    content = report(tmp_path, MarkdownEliteExporter(), papers)

    assert "no source can answer" in content
    assert "reported zero by crossref" in content
    assert "no source answered" in content


def test_a_count_with_no_provenance_at_all_admits_it(tmp_path):
    """Absent ``Citations_Source`` cannot be read as a source having answered."""
    content = report(tmp_path, MarkdownEliteExporter(), [paper("Unstamped", 12, "")])

    assert "12 (no source asked)" in content


def test_the_preamble_decomposes_the_coverage_it_claims(tmp_path):
    papers = [
        paper("a", 75, "openalex"),
        paper("b", 0, "none"),
        paper("c", 0, "unresolved"),
    ]

    content = report(tmp_path, MarkdownEliteExporter(), papers)

    assert "1 of 3 papers carry a count" in content
    assert "1 reported by their source" in content
    assert "1 carry no identifier to ask about" in content
    assert "1 could not be resolved" in content


def test_the_report_distinguishes_queried_skipped_and_rate_limited_sources(tmp_path):
    ctx = context(
        tmp_path,
        [paper("A", 0, "unresolved")],
        stats={
            "identified": {"Crossref": 12, "OpenAlex": 3, "CORE": 0, "DOAJ": 0},
            "unavailable_sources": {"CORE": "no API key"},
            "blocked_source_names": ["OpenAlex"],
            "blocked_sources": ["api.openalex.org"],
        },
    )
    ctx.query_history = [{"Source": "Crossref", "Query": "microplastics"}]

    MarkdownEliteExporter().export(ctx)
    content = next(Path(tmp_path).rglob("*.md")).read_text(encoding="utf-8")

    assert "| Crossref | 12 | queried |" in content
    assert "| OpenAlex | 3 | partially queried — rate limited; count is a floor |" in content
    assert "| CORE | 0 | not queried — no API key |" in content
    assert "| DOAJ | 0 | not queried |" in content
    assert "Rate-limited domains: api.openalex.org" in content


def test_the_impact_section_puts_the_count_next_to_where_the_ranking_put_it(tmp_path):
    """The measured disagreement — 410 citations at Relevance_Score 1.4 — stated in the report."""
    papers = [
        paper("Highly cited, badly ranked", 410, "openalex-batch", score=1.4),
        paper("Cited", 75, "openalex-batch", score=6.1),
        paper("Below the line", 3, "openalex", score=9.0),
    ]

    content = report(
        tmp_path, MarkdownEliteExporter(), papers,
        stats=IMPACT_STATS, settings={"start_year": 2021, "impact_percentile": 90},
    )

    assert "## Most Impactful Works" in content
    section = content.split("## Most Impactful Works")[1]
    assert "Highly cited, badly ranked" in section
    assert "| 410 |" in section and "| 1.4 |" in section
    assert "Below the line" not in section
    assert "counted by openalex-batch" in section


def test_the_impact_section_names_the_line_it_drew(tmp_path):
    """A cutoff that is declared can be argued with; a magic number cannot."""
    papers = [paper("a", 410, "openalex-batch")]

    content = report(
        tmp_path, MarkdownEliteExporter(), papers,
        stats=IMPACT_STATS, settings={"start_year": 2021},
    )

    assert "at or above 50 citations" in content
    assert "90th percentile of this run's 4 measured papers" in content


def test_the_two_lines_of_the_report_describe_the_same_papers(tmp_path):
    """The coverage line and the impact line count the same thing over the same set.

    They are computed in different places — the exporter summarises the papers it
    was handed, the pipeline measures the included set — so a drift between them
    is invisible until someone subtracts one from the other.
    """
    papers = [
        paper("a", 410, "openalex-batch"),
        paper("b", 75, "openalex"),
        paper("c", 0, "openalex"),
        paper("d", 0, "none"),
    ]
    stats = {"impact": {"cutoff": 50.0, "percentile": 90.0, "papers_measured": 2}}

    content = report(tmp_path, MarkdownEliteExporter(), papers, stats=stats,
                     settings={"start_year": 2021})

    assert "2 of 4 papers carry a count" in content
    assert "this run's 2 measured papers" in content


def test_a_run_with_no_counts_says_so_instead_of_dropping_the_section(tmp_path):
    """An omitted section reads as "there is nothing to say"; this is a finding about the data."""
    papers = [paper("a", 0, ""), paper("b", 0, "")]

    content = report(tmp_path, MarkdownEliteExporter(), papers)

    assert "## Most Impactful Works" in content
    assert "No source reported a citation count for this run" in content


def test_the_impact_section_declares_what_it_could_not_measure(tmp_path):
    papers = [
        paper("a", 410, "openalex-batch"),
        paper("b", 0, "none"),
        paper("c", 0, "unresolved"),
    ]

    content = report(
        tmp_path, MarkdownEliteExporter(), papers,
        stats=IMPACT_STATS, settings={"start_year": 2021},
    )

    assert "drawn from the measured ones only" in content


def test_a_title_cannot_break_the_impact_table(tmp_path):
    """A pipe in a title would add a column and shift every cell after it."""
    papers = [paper("An a | b title", 410, "openalex-batch")]

    content = report(
        tmp_path, MarkdownEliteExporter(), papers,
        stats=IMPACT_STATS, settings={"start_year": 2021},
    )

    row = [line for line in content.splitlines() if "a \\| b" in line]
    assert row and row[0].replace("\\|", "").count("|") == 7


def test_prisma_reports_the_backfill_that_produced_the_numbers(tmp_path):
    papers = [paper("a", 410, "openalex-batch")]
    stats = {
        "citation_backfill": {
            "papers_asked": 206,
            "papers_recovered": 93,
            "requests": 5,
            "unresolved": 39,
        }
    }

    content = report(tmp_path, PrismaExporter(), papers, stats=stats)

    assert "93 counts recovered over 5 batched request(s) for 206 papers" in content


def test_prisma_declares_the_citation_weight_in_force(tmp_path):
    """The weight is part of the run's configuration, so the run has to state it."""
    papers = [paper("a", 410, "openalex-batch")]

    default = report(tmp_path, PrismaExporter(), papers)
    assert "**Citation Weight:** 0.0 (0 means citations do not affect" in default

    weighted = report(
        tmp_path, PrismaExporter(), papers,
        settings={"start_year": 2021, "fusion_weights": {"keyword": 0.5, "citation": 0.5}},
    )
    assert "**Citation Weight:** 0.5" in weighted


def test_prisma_coverage_sums_to_the_included_set(tmp_path):
    papers = [
        paper("a", 75, "openalex"),
        paper("b", 120, "openalex-batch"),
        paper("c", 0, "crossref"),
        paper("d", 0, "none"),
        paper("e", 0, "unresolved"),
        paper("f", 0, ""),
    ]

    content = report(tmp_path, PrismaExporter(), papers)

    assert "**Citations Recorded:** 2 of 6" in content
    assert "(1 reported by their source, 1 filled in by a lookup)" in content
    assert "1 confirmed zero by a source, 1 unresolved, 1 with no identifier" in content
    assert "1 never asked" in content


def test_prisma_says_a_confirmed_zero_is_not_an_unanswerable_one(tmp_path):
    content = " ".join(report(tmp_path, PrismaExporter(), [paper("a", 0, "crossref")]).split())

    assert (
        "A `0` recorded as confirmed by a source and a `0` no source could "
        "answer for are different facts" in content
    )


def test_prisma_reports_the_impact_band_the_run_used(tmp_path):
    papers = [paper("a", 410, "openalex-batch")]

    content = report(tmp_path, PrismaExporter(), papers, stats=IMPACT_STATS)

    assert "**Impact Band:** 50+ citations" in content


@pytest.mark.parametrize("exporter", [MarkdownEliteExporter, PrismaExporter])
def test_an_empty_run_writes_both_reports_without_raising(tmp_path, exporter):
    """A run that found nothing still has to produce a readable file."""
    assert report(tmp_path, exporter(), [])
