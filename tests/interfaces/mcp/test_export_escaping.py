"""A exportação do agente entrega os mesmos arquivos que a do pipeline.

Havia dois serializadores para os mesmos três formatos: o de
`plugins/exporters/`, que escapa e tem testes dedicados, e o da tool MCP — que é
o caminho que o agente usa — escrevendo os valores crus. O
`test_exporters_escaping.py` passava cobrindo o caminho que não é o usado.
"""

from unittest.mock import patch

from academic_hunter.core.writing import format_bibtex_key

PAPER = {
    "Title": "A study of {braces} in ledgers",
    "Abstract": "first line\nsecond line",
    "Year": "2024",
    "Venue": "Journal of Ledgers",
    "Source": "OpenAlex",
    "DOI": "10.1/example",
    "URL": "https://example.org/1",
    "Citations": 3,
    "Relevance_Score": 8.5,
}

FORMULA_PAPER = {**PAPER, "Title": "=cmd|' /C calc'!A0"}


async def _export(papers, fmt, tmp_path, mock_ctx) -> str:
    from academic_hunter.interfaces.mcp.tools.export import export_report

    out = tmp_path / f"export.{fmt}"
    with patch("academic_hunter.interfaces.mcp.tools.export.AcademicHunter") as m_h, \
         patch("academic_hunter.interfaces.mcp.tools.export.get_project_root") as m_root:
        m_h.return_value.consolidated_results = {str(i): p for i, p in enumerate(papers)}
        m_root.return_value = tmp_path
        await export_report(mock_ctx, format=fmt, output_path=str(out))
    return out.read_text(encoding="utf-8")


async def test_bibtex_escapes_the_braces_in_a_title(tmp_path, mock_ctx):
    text = await _export([PAPER], "bibtex", tmp_path, mock_ctx)
    assert r"\{braces\}" in text, text


async def test_bibtex_writes_the_venue_as_the_journal(tmp_path, mock_ctx):
    text = await _export([PAPER], "bibtex", tmp_path, mock_ctx)
    assert "Journal of Ledgers" in text
    assert "journal = {OpenAlex}" not in text, "the database is not the journal"


async def test_ris_keeps_every_field_on_one_line(tmp_path, mock_ctx):
    text = await _export([PAPER], "ris", tmp_path, mock_ctx)
    for line in text.splitlines():
        assert not line.startswith("second line"), f"field broke across lines:\n{text}"


async def test_csv_neutralises_a_formula_in_a_title(tmp_path, mock_ctx):
    text = await _export([FORMULA_PAPER], "csv", tmp_path, mock_ctx)
    assert "'=cmd" in text, text


async def test_the_bibtex_key_is_the_one_the_agent_was_told(tmp_path, mock_ctx):
    """`paper_context` names a key and tells the agent to cite it verbatim."""
    text = await _export([PAPER], "bibtex", tmp_path, mock_ctx)
    expected = format_bibtex_key(PAPER["Title"], PAPER["Year"])
    assert f"@article{{{expected}," in text, text


def test_the_pipeline_exporter_writes_that_same_key(tmp_path):
    """Both exporters feed the same manuscript, so they cannot disagree."""
    from academic_hunter.core.ports.exporter import ExportContext
    from academic_hunter.plugins.exporters.bibtex import BibtexExporter

    BibtexExporter().export(
        ExportContext(
            papers=[dict(PAPER)],
            stats={"identified": {}, "exclusions_by_source": {}},
            settings={},
            query_history=[],
            anchors={},
            tech_strings={},
            timestamp="test_keys",
            output_dir=tmp_path,
        )
    )

    text = (tmp_path / "academic_dataset_test_keys.bib").read_text(encoding="utf-8")
    expected = format_bibtex_key(PAPER["Title"], PAPER["Year"])
    assert f"@article{{{expected}," in text, text
