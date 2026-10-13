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


def test_the_empty_csv_keeps_the_columns_of_a_populated_one(tmp_path):
    """O caminho vazio escrevia ``Database_Count`` em primeiro lugar e o povoado
    escrevia-o em último, logo o cabeçalho mudava com o resultado da corrida: um
    leitor que indexa colunas por posição lia dois datasets diferentes conforme o
    run tivesse qualificado algo ou não.
    """
    import pandas as pd

    from academic_hunter.core.models import Paper

    populated = tmp_path / "populated"
    populated.mkdir()
    CsvExporter().export(context(populated, [Paper(dict(p)) for p in EXCLUDED]))

    empty = tmp_path / "empty"
    empty.mkdir()
    CsvExporter().export(context(empty, []))

    populated_columns = list(pd.read_csv(exported_paths(populated)["csv"]).columns)
    empty_columns = list(pd.read_csv(exported_paths(empty)["csv"]).columns)

    assert empty_columns == populated_columns, (
        "the header of an empty run is not the header of a run with results: "
        f"{empty_columns} != {populated_columns}"
    )


def test_a_paper_missing_a_derived_field_does_not_take_the_dataset_with_it(tmp_path):
    """``df['Source']`` and the sort key are columns the *record* may not have.

    A paper that never went through normalisation — the shape a caller gets
    from ``export_report`` over a hand-built collection — raised ``KeyError``
    here, and the CSV for the whole run disappeared.
    """
    import pandas as pd

    CsvExporter().export(context(tmp_path, [{"Title": "Only a title"}]))

    frame = pd.read_csv(exported_paths(tmp_path)["csv"])
    assert list(frame["Title"]) == ["Only a title"]
    assert frame["Database_Count"].iloc[0] == 1


def test_a_failing_exporter_is_not_swallowed(tmp_path):
    """The run ended "successfully" with an artifact missing and nothing said.

    ``export_results`` logged the exception and moved on, so a dataset that
    could not be written left its path empty and no caller ever knew.
    """
    from types import SimpleNamespace

    import pytest

    from academic_hunter.app.exporters import HunterExporterMixin

    class Broken:
        is_prisma = False

        def export(self, ctx):
            raise RuntimeError("no space left on device")

    class Host(HunterExporterMixin):
        exporters = [Broken()]
        consolidated_results = {}
        stats = {}
        config = SimpleNamespace(
            settings={}, anchors={}, tech_strings={}, run_snapshot=lambda: None
        )
        state = SimpleNamespace(query_history=[])
        output_dir = tmp_path

    hunter = Host()

    with pytest.raises(RuntimeError, match="no space left"):
        hunter.export_results(TIMESTAMP)

