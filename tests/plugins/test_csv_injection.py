"""A célula não pode virar fórmula só porque o ataque veio indentado.

A guarda olhava o primeiro caractere do valor. Excel e LibreOffice descartam o
espaço em branco à esquerda antes de decidir o que a célula é, então
`"\\t=cmd|' /C calc'!A0"` é a mesma fórmula que a forma sem tabulação — e o
`startswith` deixava-a passar inteira. O `\\t` não é enfeite: é o vetor.
"""

import pytest

from academic_hunter.core.models.utils import neutralise_formula
from academic_hunter.plugins.exporters.base import ExportContext
from academic_hunter.plugins.exporters.csv import CsvExporter

TIMESTAMP = "test_injection"


def csv_of(tmp_path, papers):
    CsvExporter().export(
        ExportContext(
            papers=papers,
            stats={"identified": {}, "exclusions_by_source": {}},
            settings={"min_relevance_score": 0.0, "start_year": 2021},
            query_history=[],
            anchors={},
            tech_strings={},
            timestamp=TIMESTAMP,
            output_dir=tmp_path,
        )
    )
    return (tmp_path / f"academic_dataset_{TIMESTAMP}.csv").read_text(encoding="utf-8")


def paper(title):
    return {
        "Title": title,
        "Abstract": "",
        "Year": "2024",
        "Source": "OpenAlex",
        "Citations": 0,
        "DOI": "10.1/x",
        "Relevance_Score": 1.0,
        "URL": "https://example.org/x",
    }


@pytest.mark.parametrize("prefix", ["\t", "\r", "\n", "  ", "\t\r "])
@pytest.mark.parametrize("body", ["=cmd|' /C calc'!A0", "+1+1", "-1+1", "@SUM(A1)"])
def test_whitespace_before_a_formula_is_still_a_formula(prefix, body):
    assert neutralise_formula(prefix + body) == "'" + prefix + body


def test_leading_whitespace_alone_is_not_a_formula():
    """The guard must not quote — and so alter — text nobody would evaluate."""
    assert neutralise_formula("  A normal title") == "  A normal title"
    assert neutralise_formula("\t") == "\t"
    assert neutralise_formula("") == ""


def test_a_negative_number_still_reads_as_a_number():
    """`-` is in the prefix set, so this is the cost of the guard, stated."""
    assert neutralise_formula("-1.5") == "'-1.5"


def test_the_dataset_carries_the_neutralised_value(tmp_path):
    written = csv_of(tmp_path, [paper("\t=cmd|' /C calc'!A0")])

    assert "'\t=cmd" in written
    assert ",=cmd" not in written
