"""Deterministic outline generation.

Builds an article skeleton from a template plus the real data of a completed
run. Everything numeric in the output comes from the run itself — nothing is
invented. Where a section needs prose, the outline says so explicitly rather
than filling the gap with generated text, because the connected agent is the
one that writes (see the package docstring for the rationale).

The output is therefore safe to hand to an agent: it cannot hallucinate a
screening count, and any section it fills is visibly a section it wrote.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

from .style import format_table
from .templates import (
    DATA_CORPUS,
    DATA_EXCLUSIONS,
    DATA_EXPERIMENTS,
    DATA_PROSE,
    DATA_RUN_STATS,
    DATA_SOURCE_BREAKDOWN,
    ArticleTemplate,
    Section,
)

PROSE_MARKER = "<!-- TODO(agent): write this section -->"


@dataclass
class RunData:
    """Everything a completed run can tell an article.

    Deliberately a plain dataclass rather than a ``SearchState`` reference, so
    ``core.writing`` stays free of pipeline internals and can be tested without
    constructing a hunter.
    """

    topic: str = ""
    stats: Dict[str, Any] = field(default_factory=dict)
    source_breakdown: Dict[str, int] = field(default_factory=dict)
    exclusions_by_source: Dict[str, Any] = field(default_factory=dict)
    papers: List[Dict[str, Any]] = field(default_factory=list)
    experiments: Dict[str, Any] = field(default_factory=dict)
    run_timestamp: Optional[str] = None


def _screening_table(data: RunData) -> str:
    """PRISMA-style screening counts as a table."""
    stats = data.stats
    identified = stats.get("identified", {})
    total_identified = sum(identified.values()) if isinstance(identified, dict) else identified

    rows = [
        ["Identified", total_identified],
        ["Duplicates removed", stats.get("duplicates_removed", 0)],
        ["Excluded — year", stats.get("excluded_year", 0)],
        ["Excluded — anchors", stats.get("excluded_anchors", 0)],
        ["Excluded — score", stats.get("excluded_technical_score", 0)],
        ["Included in final set", stats.get("included_final", 0)],
    ]
    return format_table(
        headers=["Stage", "Papers"],
        rows=rows,
        caption="Screening flow",
        right_align=[1],
    )


def _source_table(data: RunData) -> str:
    """Per-source retrieval counts."""
    if not data.source_breakdown:
        return "<!-- no per-source breakdown available in this run -->"
    rows = [[src, count] for src, count in sorted(
        data.source_breakdown.items(), key=lambda kv: -kv[1]
    )]
    return format_table(
        headers=["Source", "Papers contributed"],
        rows=rows,
        caption="Contribution by source",
        right_align=[1],
    )


def _exclusions_table(data: RunData) -> str:
    """Why papers were dropped, by source."""
    if not data.exclusions_by_source:
        return "<!-- no exclusion breakdown available in this run -->"
    rows = []
    for src, reasons in sorted(data.exclusions_by_source.items()):
        if isinstance(reasons, dict):
            rows.append([
                src,
                reasons.get("year", 0),
                reasons.get("anchor", 0),
                reasons.get("score", 0),
            ])
    if not rows:
        return "<!-- no exclusion breakdown available in this run -->"
    return format_table(
        headers=["Source", "Year", "Anchor", "Score"],
        rows=rows,
        caption="Exclusions by source and reason",
        right_align=[1, 2, 3],
    )


def _render_data(keys: List[str], data: RunData) -> str:
    """Resolve the data sources a section asked for."""
    blocks: List[str] = []
    for key in keys:
        if key == DATA_RUN_STATS:
            if data.stats:
                blocks.append(_screening_table(data))
        elif key == DATA_SOURCE_BREAKDOWN:
            blocks.append(_source_table(data))
        elif key == DATA_EXCLUSIONS:
            blocks.append(_exclusions_table(data))
        elif key == DATA_CORPUS:
            n = len(data.papers)
            if n:
                blocks.append(
                    f"<!-- {n} papers available from this run for citation. "
                    f"Use `paper_context` to retrieve the ones relevant here. -->"
                )
        elif key == DATA_EXPERIMENTS:
            if data.experiments:
                names = ", ".join(sorted(data.experiments))
                blocks.append(
                    f"<!-- experiment results on disk: {names}. "
                    f"Cite the numbers from these files, not from memory. -->"
                )
        elif key == DATA_PROSE:
            pass  # nothing to inject — the agent writes this section
    return "\n\n".join(blocks)


def _render_section(section: Section, data: RunData) -> str:
    """Render one section, recursing into subsections."""
    heading = f"## {section.number} {section.name}" if section.number else f"## {section.name}"

    meta_bits = [f"purpose: {section.purpose}"]
    if section.target_words:
        meta_bits.append(f"target: ~{section.target_words} words")
    lines = [heading, "", f"<!-- {'; '.join(meta_bits)} -->", ""]

    rendered = _render_data(section.data, data)
    if rendered:
        lines.append(rendered)
        lines.append("")

    # Every leaf section needs prose — a table without an interpretation
    # paragraph is data, not an article. Container sections (those with
    # subsections) carry no prose of their own, so they get no marker.
    if not section.subsections:
        lines.append(PROSE_MARKER)
        lines.append("")

    for sub in section.subsections:
        lines.append(_render_section(sub, data))

    return "\n".join(lines).rstrip() + "\n"


def build_outline(
    template: ArticleTemplate,
    data: RunData,
    title: Optional[str] = None,
) -> str:
    """Build a complete article skeleton from a template and run data.

    Args:
        template: which article structure to follow.
        data: the run's real numbers and papers.
        title: article title; falls back to the run's topic.

    Returns:
        Markdown skeleton: frontmatter, every section in order, real tables
        where data exists, and explicit markers where prose is needed.
    """
    resolved_title = title or data.topic or "Untitled"
    frontmatter = "\n".join([
        "---",
        f'title: "{resolved_title}"',
        f"date: {date.today().isoformat()}",
        f"template: {template.key}",
        "status: draft",
        "---",
    ])

    header = "\n".join([
        frontmatter,
        "",
        f"<!-- Structure: {template.label} ({template.source_example}).",
        f"     Target length: ~{template.total_words} words. -->",
        "",
    ])

    body = "\n\n".join(_render_section(s, data) for s in template.sections)

    return header + body + "\n"
