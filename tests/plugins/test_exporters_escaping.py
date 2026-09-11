"""A field value must not be able to end its own record.

Measured defect: only the abstract was escaped in BibTeX and in RIS, and nothing
was escaped in the Obsidian frontmatter. A `}` in a title closed the BibTeX
field early, a newline in a title broke the RIS record, and a quote in the topic
made Obsidian read the note as having no frontmatter — the part that makes it
findable. All three fail quietly, and the file still looks written.
"""

from pathlib import Path

import pytest

from academic_hunter.plugins.exporters.base import ExportContext
from academic_hunter.plugins.exporters.bibtex import BibtexExporter
from academic_hunter.plugins.exporters.obsidian import write_obsidian_note
from academic_hunter.plugins.exporters.ris import RisExporter

HOSTILE_TITLE = 'A } brace, a \\ backslash and "a quote"'
HOSTILE_VENUE = "Journal of {Unbalanced Braces}"
HOSTILE_ABSTRACT = "Line one.\nLine two with } and \\ in it."


def paper():
    return {
        "Title": HOSTILE_TITLE,
        "Venue": HOSTILE_VENUE,
        "Abstract": HOSTILE_ABSTRACT,
        "Year": 2024,
        "URL": "https://example.org/a?b=1&c=2",
        "DOI": "10.1/a",
    }


def exported(tmp_path, exporter, papers):
    context = ExportContext(
        papers=papers,
        stats={"identified": {}, "exclusions_by_source": {}},
        settings={"min_relevance_score": 3.5, "start_year": 2021},
        query_history=[],
        anchors={},
        tech_strings={},
        timestamp="test_run",
        output_dir=tmp_path,
    )
    exporter.export(context)
    return [f for f in Path(tmp_path).rglob("*") if f.suffix in (".bib", ".ris")][0]


# ── BibTeX ──────────────────────────────────────────────────────────────────


def field_line(content, field):
    return next(
        line for line in content.splitlines() if line.strip().startswith(f"{field} = {{")
    )


def test_a_brace_in_the_title_cannot_close_the_field_early(tmp_path):
    """The record must still have all six fields, in order.

    An unescaped `}` ends the field right there: the rest of the title becomes
    record-level garbage and BibTeX reports a syntax error somewhere else.
    """
    content = exported(tmp_path, BibtexExporter(), [paper()]).read_text(encoding="utf-8")

    fields = [
        line.split(" = ")[0].strip()
        for line in content.splitlines()
        if " = " in line and not line.startswith("@")
    ]
    assert fields == ["title", "journal", "year", "url", "doi", "abstract"]


def test_every_field_is_escaped_not_only_the_abstract(tmp_path):
    content = exported(tmp_path, BibtexExporter(), [paper()]).read_text(encoding="utf-8")

    for field in ("title", "journal"):
        assert "\\}" in field_line(content, field), f"{field} was written raw"

    # The abstract spans lines (a value may), so it is checked over the record.
    assert "\\}" in content.split("abstract = ")[1]


def test_a_backslash_in_a_field_is_neutralised(tmp_path):
    content = exported(tmp_path, BibtexExporter(), [paper()]).read_text(encoding="utf-8")

    assert "\\textbackslash{}" in field_line(content, "title")


def test_the_escaping_runs_once_over_the_original_text(tmp_path):
    """Two chained `.replace` calls would escape the escapes."""
    content = exported(tmp_path, BibtexExporter(), [paper()]).read_text(encoding="utf-8")

    assert "\\\\textbackslash" not in content
    assert "\\\\}" not in content


def test_a_clean_record_is_left_alone(tmp_path):
    clean = {
        "Title": "A normal title",
        "Venue": "A journal",
        "Abstract": "Plain text.",
        "Year": 2024,
    }
    content = exported(tmp_path, BibtexExporter(), [clean]).read_text(encoding="utf-8")

    assert "title = {A normal title}," in content
    assert "\\{" not in content and "\\}" not in content


# ── RIS ─────────────────────────────────────────────────────────────────────


def test_a_newline_in_a_title_does_not_split_the_record(tmp_path):
    content = exported(
        tmp_path, RisExporter(), [{**paper(), "Title": "First line\nSecond line"}]
    ).read_text(encoding="utf-8")

    title_lines = [line for line in content.splitlines() if line.startswith("TI  - ")]
    assert len(title_lines) == 1
    assert title_lines[0] == "TI  - First line Second line"


def test_every_ris_line_belongs_to_a_known_tag(tmp_path):
    """A value that breaks its line produces a line the reader cannot place."""
    content = exported(tmp_path, RisExporter(), [paper()]).read_text(encoding="utf-8")

    tags = {
        line.split("  - ")[0]
        for line in content.splitlines()
        if line.strip()
    }
    assert tags <= {"TY", "TI", "JO", "PY", "UR", "DO", "N2", "ER"}


def test_the_record_ends_where_it_should(tmp_path):
    content = exported(tmp_path, RisExporter(), [paper()]).read_text(encoding="utf-8")

    assert content.count("TY  - JOUR") == 1
    assert content.count("ER  - ") == 1


# ── Obsidian frontmatter ────────────────────────────────────────────────────


def frontmatter_of(path):
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---")[1])


def test_a_quote_in_the_topic_does_not_break_the_frontmatter(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()

    parsed = frontmatter_of(write_obsidian_note(str(vault), 'A "quoted" topic', "body"))

    assert parsed["title"] == 'A "quoted" topic'


def test_a_newline_in_the_topic_does_not_break_the_frontmatter(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()

    parsed = frontmatter_of(
        write_obsidian_note(str(vault), "First\nsecond: injected", "body")
    )

    assert parsed["title"] == "First second: injected"
    assert parsed["type"] == "source", "the keys after the title were lost"


def test_a_clean_topic_is_written_as_given(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()

    parsed = frontmatter_of(write_obsidian_note(str(vault), "Quantum error correction", "body"))

    assert parsed["title"] == "Quantum error correction"
    assert parsed["tags"] == ["academic-hunter", "research"]
