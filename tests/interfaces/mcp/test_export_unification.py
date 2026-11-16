"""One writer per format — and the assertion that would notice it coming undone.

The pipeline wrote its ``academic_dataset_*`` files through
``plugins/exporters`` and the ``export_report`` tool rendered its own copies in
``interfaces/mcp/tools/export.py``. They had drifted: the same run's RIS carried
``N2`` from one and ``AB`` from the other.

Comparing the two files byte for byte is the obvious test and the weaker one: it
passes today on two writers that happen to agree. The sentinel test below
replaces the renderer outright and asserts both paths emit exactly that, which is
a claim about there being one writer at all rather than about two agreeing.
"""

from unittest.mock import patch

import pytest

from academic_hunter.core.writing import renderers
from academic_hunter.plugins.exporters.base import ExportContext
from academic_hunter.plugins.exporters.bibtex import BibtexExporter
from academic_hunter.plugins.exporters.csv import CsvExporter
from academic_hunter.plugins.exporters.ris import RisExporter

PAPERS = [
    {
        "Title": "Ledger settlement in wholesale payments",
        "Authors": "Silva, A.; Costa, B.",
        "Abstract": "We study atomic settlement.",
        "Year": 2024,
        "URL": "https://example.org/a?b=1&c=2",
        "DOI": "10.1/a",
        "Venue": "Journal of {Unbalanced Braces}",
        "Source": "OpenAlex, Crossref",
        "Citations": 12,
        "Relevance_Score": 8.5,
        "_kw_score": 4.0,
    },
    {
        "Title": "No year, no venue, no authors",
        "Abstract": "",
        "Year": "",
        "URL": "",
        "DOI": "",
        "Venue": "",
        "Source": "arXiv",
        "Citations": 0,
        "Relevance_Score": 3.5,
        "_kw_score": 0.5,
    },
    {
        "Title": "=cmd|' /C calc'!A0",
        "Authors": "Solo, C.",
        "Abstract": "Second line\nwith a break.",
        "Year": "2024-05-01",
        "URL": "https://example.org/c",
        "DOI": "10.1/c",
        "Venue": "Another Venue",
        "Source": "DOAJ",
        "Citations": 3,
        "Relevance_Score": 3.5,
        "_kw_score": 0.5,
    },
]

CASES = [
    ("bibtex", "bib", "render_bibtex", BibtexExporter),
    ("ris", "ris", "render_ris", RisExporter),
    ("csv", "csv", "render_csv", CsvExporter),
]


def context(tmp_path, papers):
    return ExportContext(
        papers=papers,
        stats={"identified": {}, "exclusions_by_source": {}},
        settings={"min_relevance_score": 3.5, "start_year": 2021},
        query_history=[],
        anchors={},
        tech_strings={},
        timestamp="test_run",
        output_dir=tmp_path,
    )


async def via_tool(tmp_path, mock_ctx, papers, fmt):
    from academic_hunter.interfaces.mcp.tools.export import export_report

    out = tmp_path / f"tool.{fmt}"
    with (
        patch("academic_hunter.interfaces.mcp.tools.export.AcademicHunter") as m_h,
        patch("academic_hunter.interfaces.mcp.tools.export.get_project_root") as m_root,
    ):
        m_h.return_value.consolidated_results = {str(i): paper for i, paper in enumerate(papers)}
        m_root.return_value = tmp_path
        await export_report(mock_ctx, format=fmt, output_path=str(out))
    return out.read_text(encoding="utf-8")


@pytest.mark.parametrize("fmt,ext,attribute,exporter", CASES)
async def test_both_paths_write_whatever_the_one_renderer_returns(
    monkeypatch, tmp_path, mock_ctx, fmt, ext, attribute, exporter
):
    """Replacing the renderer replaces both files, so there is one writer."""
    sentinel = f"SENTINEL-{fmt}"
    monkeypatch.setattr(renderers, attribute, lambda papers: sentinel)

    exporter().export(context(tmp_path, PAPERS))
    from_pipeline = (tmp_path / f"academic_dataset_test_run.{ext}").read_text()
    from_tool = await via_tool(tmp_path, mock_ctx, PAPERS, fmt)

    assert from_pipeline == sentinel
    assert from_tool == sentinel


@pytest.mark.parametrize("fmt,ext,attribute,exporter", CASES)
async def test_the_two_paths_produce_the_same_bytes(tmp_path, mock_ctx, fmt, ext, attribute, exporter):
    exporter().export(context(tmp_path, PAPERS))

    from_pipeline = (tmp_path / f"academic_dataset_test_run.{ext}").read_text()

    assert await via_tool(tmp_path, mock_ctx, PAPERS, fmt) == from_pipeline


@pytest.mark.parametrize("fmt,ext,attribute,exporter", CASES)
async def test_neither_path_depends_on_the_order_its_rows_arrived_in(tmp_path, mock_ctx, fmt, ext, attribute, exporter):
    """The tool used to keep the order it was handed, which came from a read_csv."""
    forward = await via_tool(tmp_path, mock_ctx, PAPERS, fmt)
    backward = await via_tool(tmp_path, mock_ctx, list(reversed(PAPERS)), fmt)

    assert forward == backward

    exporter().export(context(tmp_path, list(reversed(PAPERS))))

    assert (tmp_path / f"academic_dataset_test_run.{ext}").read_text() == forward


async def test_the_tool_keeps_no_writer_of_its_own():
    """A private writer reappearing is how the two drifted apart the first time."""
    from academic_hunter.interfaces.mcp.tools import export as export_module

    assert not hasattr(export_module, "_write_bibtex")
    assert not hasattr(export_module, "_write_ris")
