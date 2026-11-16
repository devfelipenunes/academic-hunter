"""One renderer per record format: papers in, the complete text of a file out.

These are pure. They take papers and return a string; they open nothing, print
nothing, and know nothing about where a run writes. That separation is the point:
*where* a file goes is each caller's business — the pipeline writes into the
run's directory and the ``export_report`` tool writes wherever the agent asked —
but the bytes are one decision, made here.

They were two decisions until now. ``plugins/exporters/`` rendered the text for
the run directory and ``interfaces/mcp/tools/export.py`` rendered its own for the
tool, already drifted: the same run exported to RIS carried ``N2`` from the
pipeline and ``AB`` from the tool, and a BibTeX entry listed ``author`` before
``title`` on one side and after it on the other. Each was defensible alone;
together they made "the run's RIS" and "the exported RIS" two different files.

Where the two disagreed, the pipeline's shape won: it is what the end-to-end
tests read by name, and its field order and RIS tag are the ones pinned. Two
values did not survive that choice. An unknown year was written as the run's
``start_year`` and an unknown venue as ``Unknown``, and a bibliography that
states a year no source reported cites a paper that does not exist. Empty values
are omitted instead, and a year is written only when it carries four digits.

Formats differ on that last point for a reason: a line-oriented record can drop
what it does not know, while a table cannot — a row is positional, so the CSV
fills from ``FIELD_SCHEMA`` the way it always has.
"""

import csv
import io
import json
from typing import Any, List, Mapping, Sequence

from ..models.authors import split_authors
from ..models.schema import FIELD_SCHEMA
from ..models.utils import (
    bibtex_authors,
    escape_bibtex,
    neutralise_formula,
    one_line,
    paper_order_key,
    strip_abstract_placeholder,
)
from .style import paper_citation_key

DERIVED_COLUMNS = ("Database_Count", "Has_Abstract")


def _ordered(papers: Sequence[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    """The run's papers in the one order every format agrees on.

    Sorting here rather than at the call sites is what stops the tool's output
    from depending on the order its rows arrived in — which, for an export off
    ``_load_latest_papers``, is whatever ``read_csv`` happened to produce.

    It also has to happen before rows are built rather than after: a sort applied
    to the finished table is unstable by default, so the rows of papers sharing a
    score came out in an undefined order, and it stayed undefined under a stable
    sort because the order the papers arrive in is itself a product of concurrent
    mining. Measured on one run: 287 of 310 papers sat inside a tie, and two runs
    of the same corpus disagreed on 214 rows.
    """
    return sorted(papers, key=paper_order_key)


def _field(paper: Mapping[str, Any], name: str) -> str:
    value = paper.get(name, paper.get(name.lower(), ""))
    return "" if value is None else str(value).strip()


def _year(value: Any) -> str:
    """Four digits, or nothing.

    ``str(value)[:4]`` alone turned an absent year into ``""`` and then into the
    literal ``2021`` further down; a truncated ``"2024-05-01"`` is a year, but
    ``"N/A"`` and ``"forthcoming"`` are not, and neither is a start year the
    pipeline supplied on the paper's behalf.
    """
    head = str(value or "").strip()[:4]
    return head if head.isdigit() else ""


def render_bibtex(papers: Sequence[Mapping[str, Any]]) -> str:
    """The run as BibTeX, one ``@article`` per paper, blank line between."""
    entries = []
    for paper in _ordered(papers):
        fields = (
            ("title", _field(paper, "Title")),
            ("author", bibtex_authors(paper.get("Authors", paper.get("author", "")))),
            ("journal", _field(paper, "Venue")),
            ("year", _year(paper.get("Year"))),
            ("url", _field(paper, "URL")),
            ("doi", _field(paper, "DOI")),
            ("abstract", _field(paper, "Abstract")),
        )
        lines = [f"  {name} = {{{escape_bibtex(value)}}}" for name, value in fields if value]
        entries.append("@article{" + paper_citation_key(paper) + ",\n" + ",\n".join(lines) + "\n}")
    return "".join(f"{entry}\n\n" for entry in entries)


def render_ris(papers: Sequence[Mapping[str, Any]]) -> str:
    """The run as RIS, one record per paper, blank line between.

    The abstract travels under ``N2``. The RIS specification knows both ``N2``
    and ``AB`` for it, and this file used to say ``N2`` while the tool said
    ``AB``; a reader that wants the other tag should be given both, never a
    swap, because ``N2`` is what the run's own exporters have always written.
    """
    records = []
    for paper in _ordered(papers):
        lines = ["TY  - JOUR"]
        title = _field(paper, "Title")
        if title:
            lines.append(f"TI  - {one_line(title)}")
        authors = paper.get("Authors", paper.get("author", ""))
        for author in split_authors(authors):
            lines.append(f"AU  - {one_line(author)}")
        for tag, value in (
            ("JO", _field(paper, "Venue")),
            ("PY", _year(paper.get("Year"))),
            ("UR", _field(paper, "URL")),
            ("DO", _field(paper, "DOI")),
            ("N2", _field(paper, "Abstract")),
        ):
            if value:
                lines.append(f"{tag}  - {one_line(value)}")
        lines.append("ER  - ")
        records.append("\n".join(lines))
    return "".join(f"{record}\n\n" for record in records)


def _csv_columns(papers: Sequence[Mapping[str, Any]]) -> List[str]:
    """The columns of the dataset, in the order a reader already expects.

    Every key the papers carry, in the order it first appears — which is how the
    score internals (``_kw_score`` and friends) reach the CSV, and the end-to-end
    tests read them by name — then every schema field no paper carried, then the
    two derived ones.
    """
    columns: List[str] = []
    seen = set()
    for paper in papers:
        for key in paper:
            if key not in seen:
                seen.add(key)
                columns.append(key)
    columns.extend(field for field in FIELD_SCHEMA if field not in seen)
    columns.extend(DERIVED_COLUMNS)
    return columns


def render_csv(papers: Sequence[Mapping[str, Any]]) -> str:
    """The dataset, one row per study.

    An empty run still writes its header: a file a reader can open and find no
    rows in beats a zero-byte file that some readers refuse, and the header is
    the same one a populated run writes, so a reader taking columns by position
    cannot be reading a different dataset.

    ``Has_Abstract`` is derived for the same reason ``Database_Count`` is: a row
    whose abstract cell is empty is a row the anchor gate and the term tally
    could only read through its title, and no column said so.
    """
    ordered = _ordered(papers)
    columns = _csv_columns(ordered)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)

    for paper in ordered:
        row = []
        for column in columns:
            if column == "Database_Count":
                source = str(paper.get("Source") or "")
                parts = [part.strip() for part in source.split(",") if part.strip()]
                value = len(parts) if source else 1
            elif column == "Has_Abstract":
                value = bool(strip_abstract_placeholder(paper.get("Abstract")).strip())
            else:
                spec = FIELD_SCHEMA.get(column)
                value = paper.get(column, spec["default"] if spec else None)
            row.append(neutralise_formula(value))
        writer.writerow(row)
    return buffer.getvalue()


def render_screening_candidates_csv(
    papers: Sequence[Mapping[str, Any]], inclusion_key: str, threshold: float
) -> str:
    """Render every scored candidate with machine and human screening fields.

    This is deliberately separate from the final dataset: papers below the
    automatic cut remain visible for recall audits and manual adjudication.
    """
    audited = []
    for paper in papers:
        row = dict(paper)
        try:
            score = float(row.get(inclusion_key) or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        accepted = score >= threshold
        row["Automated_Screening"] = "include" if accepted else "below_threshold"
        row["Automated_Screening_Reason"] = (
            f"{inclusion_key}={score:g}; threshold={threshold:g}"
        )
        row["Human_Decision"] = ""
        row["Human_Reviewer"] = ""
        row["Human_Notes"] = ""
        audited.append(row)
    return render_csv(audited)


def render_screening_exclusions_csv(
    papers: Sequence[Mapping[str, Any]],
) -> str:
    """Render unique papers rejected before scoring for anchor-recall audits."""
    audited = []
    for paper in papers:
        row = dict(paper)
        row["Automated_Screening"] = "excluded_before_score"
        row["Human_Decision"] = ""
        row["Human_Reviewer"] = ""
        row["Human_Notes"] = ""
        audited.append(row)
    return render_csv(audited)


def render_json(papers: Sequence[Mapping[str, Any]]) -> str:
    """The run as JSON, for the caller that wants the rows rather than a table.

    ``default=str`` is not decoration: papers read back from a saved CSV carry
    numpy scalars, which the encoder refuses outright.
    """
    return json.dumps(list(_ordered(papers)), indent=2, ensure_ascii=False, default=str)
