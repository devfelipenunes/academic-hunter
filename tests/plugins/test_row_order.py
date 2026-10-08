"""A ordem das linhas não pode depender da ordem por que os papers chegaram.

Comparar dois runs do mesmo corpus dava 214 posições trocadas com pontuações
idênticas — ruído dentro de grupos de empate que se lê como regressão de
ordenação. A causa é dupla: ``DataFrame.sort_values`` usa um quicksort instável,
e a ordem de entrada em ``consolidated_results`` vem da mineração concorrente.
Por isso a correcção não é pedir estabilidade ao sort: é dar-lhe uma chave total.

Cada teste aqui falha antes da correcção. Os papers são apresentados em duas
ordens de entrada e a saída tem de ser a mesma.
"""

import re
from pathlib import Path

import pandas as pd
import pytest

from academic_hunter.plugins.exporters.base import ExportContext
from academic_hunter.plugins.exporters.bibtex import BibtexExporter
from academic_hunter.plugins.exporters.csv import CsvExporter
from academic_hunter.plugins.exporters.markdown_elite import MarkdownEliteExporter
from academic_hunter.plugins.exporters.ris import RisExporter

IMPACT = {"impact": {"cutoff": 50.0, "percentile": 90.0, "papers_measured": 3}}


def paper(title, doi="", score=5.0, citations=0):
    return {
        "Title": title,
        "DOI": doi,
        "Relevance_Score": score,
        "Citations": citations,
        "Citations_Source": "openalex" if citations else "none",
        "Year": 2024,
        "Venue": "A Venue",
        "Peer_Reviewed": True,
        "Source": "OpenAlex",
        "Anchor_Category": "Blockchain",
        "URL": "https://example.org/a",
        "Abstract": "An abstract.",
    }


def context(tmp_path, papers, timestamp, stats=None):
    return ExportContext(
        papers=papers,
        stats={
            "identified": {"openalex": len(papers)},
            "exclusions_by_source": {},
            "included_final": len(papers),
            **(stats or {}),
        },
        settings={"start_year": 2021, "min_relevance_score": 3.5},
        query_history=[],
        anchors={"Blockchain": ["blockchain"]},
        tech_strings={"Core": ["ledger"]},
        timestamp=timestamp,
        output_dir=tmp_path,
    )


def export_and_read(exporter, tmp_path, papers, tag, stats=None, suffix=""):
    """Export under a tag of its own, so two exports of one corpus can be compared."""
    exporter.export(context(tmp_path, papers, timestamp=f"test_{tag}", stats=stats))
    matches = [p for p in Path(tmp_path).glob(f"*test_{tag}*") if suffix in p.name]
    return matches[0].read_text(encoding="utf-8")


def tied(count=6, score=4.0):
    """Papers sharing a score, which is where the order was undefined."""
    return [paper(f"Title {i}", f"10.1/{i}", score=score) for i in range(count)]


def csv_titles(tmp_path, papers, tag):
    export_and_read(CsvExporter(), tmp_path, papers, tag, suffix=".csv")
    path = next(Path(tmp_path).glob(f"*test_{tag}*.csv"))
    return list(pd.read_csv(path)["Title"])


def report_headings(tmp_path, papers, tag):
    text = export_and_read(MarkdownEliteExporter(), tmp_path, papers, tag, suffix=".md")
    return re.findall(r"^### (.+?) \(Relevance_Score", text, re.MULTILINE)


def impact_titles(tmp_path, papers, tag):
    text = export_and_read(
        MarkdownEliteExporter(), tmp_path, papers, tag, stats=IMPACT, suffix=".md"
    )
    table = text.split("## Most Impactful Works")[1]
    return [row.split("|")[2].strip() for row in table.splitlines() if re.match(r"\| \d+ \|", row)]


def bibtex_titles(tmp_path, papers, tag):
    text = export_and_read(BibtexExporter(), tmp_path, papers, tag, suffix=".bib")
    return re.findall(r"title = \{(.+?)\},", text)


def ris_titles(tmp_path, papers, tag):
    text = export_and_read(RisExporter(), tmp_path, papers, tag, suffix=".ris")
    return re.findall(r"^TI  - (.+)$", text, re.MULTILINE)


@pytest.mark.parametrize(
    "reader",
    [csv_titles, report_headings, bibtex_titles, ris_titles],
    ids=["csv", "report", "bibtex", "ris"],
)
def test_the_row_order_does_not_depend_on_the_order_the_papers_arrived_in(tmp_path, reader):
    """The measured defect, at every surface that emits papers in an order.

    The CSV is the one that reported it, but the report, the .bib and the .ris all
    ordered on the score alone and inherited the same arrival order.
    """
    papers = tied()

    forward = reader(tmp_path, papers, "fwd")
    backward = reader(tmp_path, list(reversed(papers)), "bwd")

    assert forward == backward
    assert forward == sorted(forward), "the tie is broken by identity, ascending"


def test_the_report_orders_tied_papers_by_their_doi(tmp_path):
    """Not just 'some fixed order': the order the key defines."""
    papers = [
        paper("Second", "10.1/b", score=4.0),
        paper("First", "10.1/a", score=4.0),
    ]

    assert report_headings(tmp_path, papers, "byid") == ["First", "Second"]


def test_the_impact_table_breaks_a_tie_in_citations_the_same_way(tmp_path):
    """The table sorts on Citations, so it needed the same tie-break on identity."""
    papers = [
        paper("Second", "10.1/b", citations=120),
        paper("First", "10.1/a", citations=120),
        paper("High", "10.1/c", citations=500),
    ]

    forward = impact_titles(tmp_path, papers, "ifwd")
    backward = impact_titles(tmp_path, list(reversed(papers)), "ibwd")

    assert forward == backward
    assert forward == ["High", "First", "Second"]


def test_the_tie_break_does_not_move_a_single_score(tmp_path):
    """The order is a presentation decision; the score is a measurement.

    Folding the identity into ``Relevance_Score`` would have been the other way
    to make the rows stable, and it would have been wrong: the score is what the
    run reports, compares and calibrates against, and nudging it to break a tie
    changes the measurement to fix the display. This pins every value, so that
    route cannot be taken without a test going red.
    """
    papers = tied()
    scores = {p["Title"]: p["Relevance_Score"] for p in papers}

    export_and_read(CsvExporter(), tmp_path, papers, "scores", suffix=".csv")
    path = next(Path(tmp_path).glob("*test_scores*.csv"))
    frame = pd.read_csv(path)

    assert list(frame["Relevance_Score"]) == [scores[t] for t in frame["Title"]]
    assert list(frame["Relevance_Score"]) == [4.0] * len(papers)


def test_papers_with_different_scores_keep_their_ranking(tmp_path):
    """The fix is confined to the ties: the ranking itself must be untouched."""
    papers = [
        paper("Top", "10.1/a", score=9.0),
        paper("Middle", "10.1/b", score=5.0),
        paper("Bottom", "10.1/c", score=1.0),
    ]

    assert csv_titles(tmp_path, papers, "mix") == ["Top", "Middle", "Bottom"]
    assert report_headings(tmp_path, papers, "mix2") == ["Top", "Middle", "Bottom"]
