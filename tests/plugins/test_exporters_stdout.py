"""Exporters must never write to stdout.

Over stdio — the default transport — stdout **is** the JSON-RPC channel, so a
``print()`` corrupts the client's framing. Invisible to any other kind of test:
the exporters worked, they just wrote to the wrong stream.
"""

import contextlib
import io
from pathlib import Path

import pytest

from academic_hunter.core.ports.exporter import ExportContext
from academic_hunter.plugins.exporters.bibtex import BibtexExporter
from academic_hunter.plugins.exporters.csv import CsvExporter
from academic_hunter.plugins.exporters.markdown_elite import MarkdownEliteExporter
from academic_hunter.plugins.exporters.prisma import PrismaExporter
from academic_hunter.plugins.exporters.ris import RisExporter

PAPERS = [
    {
        "Title": "A Study of Ledgers",
        "Abstract": "We study ledgers, and commas, and other things.",
        "Year": "2024",
        "Source": "OpenAlex",
        "Citations": 3,
        "DOI": "10.1/example",
        "Relevance_Score": 8.5,
        "URL": "https://example.org/1",
    },
    {
        "Title": "Second Paper",
        "Abstract": "Another abstract.",
        "Year": "2023",
        "Source": "Crossref",
        "Citations": 1,
        "DOI": "10.1/second",
        "Relevance_Score": 6.0,
        "URL": "https://example.org/2",
    },
]

EXPORTERS = [
    CsvExporter,
    BibtexExporter,
    RisExporter,
    PrismaExporter,
    MarkdownEliteExporter,
]


def make_context(output_dir: Path) -> ExportContext:
    """A context with one of everything, so no exporter bails out early.

    ``timestamp`` contains "test" so ``_get_run_dir`` writes straight into the
    tmp dir instead of nesting a ``run_<ts>/``.
    """
    return ExportContext(
        papers=[dict(p) for p in PAPERS],
        stats={
            "identified": {"OpenAlex": 10},
            "duplicates_removed": 2,
            "excluded_year": 0,
            "excluded_anchors": 0,
            "excluded_technical_score": 0,
            "included_final": 2,
            "exclusions_by_source": {},
        },
        settings={"min_relevance_score": 3.5, "start_year": 2021},
        # The shape the connectors append (see `plugins/connectors/core_ac.py`).
        query_history=[{"Source": "OpenAlex", "Query": "ledgers"}],
        anchors={"Cat": ["ledger"]},
        tech_strings={"Tech": ["ledger"]},
        timestamp="test_run",
        output_dir=output_dir,
    )


@pytest.mark.parametrize("exporter_cls", EXPORTERS, ids=lambda c: c.__name__)
def test_exporter_writes_nothing_to_stdout(exporter_cls, tmp_path):
    captured = io.StringIO()

    with contextlib.redirect_stdout(captured):
        exporter_cls().export(make_context(tmp_path))

    assert captured.getvalue() == "", (
        f"{exporter_cls.__name__} wrote to stdout, which is the MCP transport "
        f"channel over stdio: {captured.getvalue()!r}"
    )


@pytest.mark.parametrize("exporter_cls", EXPORTERS, ids=lambda c: c.__name__)
def test_exporter_still_produces_its_file(exporter_cls, tmp_path):
    """The other half: silence must not mean it stopped working."""
    exporter_cls().export(make_context(tmp_path))

    produced = list(tmp_path.iterdir())
    assert produced, f"{exporter_cls.__name__} produced no file"


def test_a_formula_in_a_field_is_neutralised(tmp_path):
    """A title from a third-party API is not ours to trust.

    Opened in Excel or LibreOffice, `=...` in a cell is evaluated.
    """
    context = make_context(tmp_path)
    context.papers = [
        {
            "Title": '=HYPERLINK("http://evil.example","click")',
            "Abstract": "+1+1",
            "Source": "OpenAlex",
            "Year": "2024",
            "Relevance_Score": 5.0,
        }
    ]

    CsvExporter().export(context)

    written = next(tmp_path.glob("*.csv")).read_text()
    assert '"\'' in written or "'=" in written, f"not neutralised: {written!r}"
    assert ",=HYPERLINK" not in written


def test_an_empty_run_does_not_print_either(tmp_path):
    """The CSV exporter's early return used to be the loudest of the prints."""
    context = make_context(tmp_path)
    context.papers = []
    captured = io.StringIO()

    with contextlib.redirect_stdout(captured):
        CsvExporter().export(context)

    assert captured.getvalue() == ""
