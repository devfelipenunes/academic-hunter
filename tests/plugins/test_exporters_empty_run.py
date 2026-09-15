"""Um run que não qualificou nada não pode deixar os excluídos nos arquivos.

O pipeline exportava a coleção inteira e só então aplicava o limiar. Quando o
conjunto filtrado ficava vazio os exportadores saíam cedo — sem escrever — e o
arquivo do export anterior sobrevivia. Quem lia o CSV encontrava ali, como
resultado, exatamente os papers que o limiar tinha excluído.
"""

from academic_hunter.core.ports.exporter import ExportContext
from academic_hunter.plugins.exporters.bibtex import BibtexExporter
from academic_hunter.plugins.exporters.csv import CsvExporter
from academic_hunter.plugins.exporters.ris import RisExporter

EXCLUDED = [
    {
        "Title": "Excluded Paper",
        "Abstract": "Below the threshold.",
        "Year": "2024",
        "Source": "OpenAlex",
        "Citations": 0,
        "DOI": "10.1/excluded",
        "Relevance_Score": 1.0,
        "URL": "https://example.org/x",
    },
]

TIMESTAMP = "test_empty_run"


def context(output_dir, papers):
    return ExportContext(
        papers=papers,
        stats={
            "identified": {"OpenAlex": 1},
            "duplicates_removed": 0,
            "excluded_year": 0,
            "excluded_anchors": 0,
            "excluded_technical_score": 1 if not papers else 0,
            "included_final": 0 if not papers else 1,
            "exclusions_by_source": {},
        },
        settings={"min_relevance_score": 5.0, "start_year": 2021},
        query_history=[],
        anchors={},
        tech_strings={},
        timestamp=TIMESTAMP,
        output_dir=output_dir,
    )


def exported_paths(tmp_path):
    return {
        "csv": tmp_path / f"academic_dataset_{TIMESTAMP}.csv",
        "bib": tmp_path / f"academic_dataset_{TIMESTAMP}.bib",
        "ris": tmp_path / f"academic_dataset_{TIMESTAMP}.ris",
    }


def test_the_unfiltered_export_is_overwritten_when_nothing_qualifies(tmp_path):
    for exporter in (CsvExporter(), BibtexExporter(), RisExporter()):
        exporter.export(context(tmp_path, [dict(p) for p in EXCLUDED]))

    paths = exported_paths(tmp_path)
    assert "Excluded Paper" in paths["csv"].read_text(encoding="utf-8")

    for exporter in (CsvExporter(), BibtexExporter(), RisExporter()):
        exporter.export(context(tmp_path, []))

    for kind, path in paths.items():
        assert path.exists(), f"the {kind} artifact of this run is missing"
        assert "Excluded Paper" not in path.read_text(encoding="utf-8"), (
            f"{path.name} still holds a paper this run excluded"
        )


def test_the_empty_csv_still_parses_as_a_dataset(tmp_path):
    """The readers run `pd.read_csv` on it; a zero-byte file would warn."""
    import pandas as pd

    CsvExporter().export(context(tmp_path, []))

    frame = pd.read_csv(exported_paths(tmp_path)["csv"])
    assert len(frame) == 0
    assert "Title" in frame.columns
