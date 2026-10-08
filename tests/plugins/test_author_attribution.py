"""A autoria atravessa as camadas, da API até à referência exportada.

Medição no run entregue (`310` papers): as entradas do `.bib` traziam `title`,
`journal`, `year`, `url`, `doi` e `abstract` — e **nenhuma** `author`. Não era
uma perda a meio do caminho: `grep author` sobre os seis connectors devolvia zero
linhas, logo o campo nunca chegava a ser lido. As APIs trazem-no; o código é que
o ignorava.

O teste pina a cadeia inteira porque cada elo passa sem os outros: o connector
que lê o campo, as duas passagens que o transportam pelo pipeline, e as
superfícies que o imprimem. Um connector que volta a ignorar a autoria, ou uma
delas que a descarta, tem de falhar aqui.

**Limite declarado:** CORE e DOAJ não publicam autoria. Um paper cuja única
cópia venha de um deles continua sem autores, e o último teste diz isso em vez
de passar por omissão.
"""

import json
import threading
from pathlib import Path

import pytest

from academic_hunter.core.models import Paper
from academic_hunter.core.models.strategies import strategy_authors
from academic_hunter.plugins.connectors.arxiv import ArxivConnector
from academic_hunter.plugins.connectors.crossref import CrossrefConnector
from academic_hunter.plugins.connectors.openalex import OpenAlexConnector
from academic_hunter.plugins.connectors.semanticscholar import SemanticScholarConnector
from academic_hunter.plugins.exporters.base import ExportContext
from academic_hunter.plugins.exporters.bibtex import BibtexExporter
from academic_hunter.plugins.exporters.csv import CsvExporter
from academic_hunter.plugins.exporters.markdown_elite import MarkdownEliteExporter
from academic_hunter.plugins.exporters.ris import RisExporter

TWO_AUTHORS = "Lovelace, Ada; Berg, Jan van der"


def connector(cls, monkeypatch, payload=None, text=None, **settings):
    made = cls(
        cache=None,
        settings=settings,
        query_history=[],
        lock=threading.RLock(),
        semaphore=threading.Semaphore(1),
        use_cache=False,
    )
    calls = []

    if text is not None:
        class Response:
            def __init__(self, body):
                self.text = body

        def raw(url, **kwargs):
            calls.append(url)
            return Response(text)

        monkeypatch.setattr(made, "_raw_request", raw)
    else:
        def make(url, **kwargs):
            calls.append((url, kwargs.get("params")))
            return payload

        monkeypatch.setattr(made, "_make_request", make)

    made.calls = calls
    return made


CROSSREF_ITEM = {
    "title": ["Ledgers at scale"],
    "author": [
        {"family": "Lovelace", "given": "Ada"},
        {"family": "Berg", "given": "Jan van der"},
        {"name": "The Ledger Consortium"},
    ],
    "container-title": ["Journal of Ledgers"],
    "issued": {"date-parts": [[2024, 1, 1]]},
    "type": "journal-article",
    "DOI": "10.1234/ledger",
}

OPENALEX_ITEM = {
    "display_name": "Ledgers at scale",
    "authorships": [
        {"author": {"display_name": "Ada Lovelace"}},
        {"author": {"display_name": "Jan van der Berg"}},
    ],
    "cited_by_count": 3,
    "doi": "https://doi.org/10.1234/ledger",
    "type": "article",
    "publication_year": 2024,
}

ARXIV_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <published>2024-01-01T00:00:00Z</published>
    <title>Ledgers at scale</title>
    <summary>We study ledgers.</summary>
    <author><name>Ada Lovelace</name></author>
    <author><name>Jan van der
      Berg</name></author>
  </entry>
</feed>
"""


def test_crossref_reads_the_authors_it_already_sends(monkeypatch):
    """`author` chega em metades, e um organismo chega como `name`."""
    made = connector(
        CrossrefConnector, monkeypatch, payload={"message": {"items": [CROSSREF_ITEM]}}
    )

    papers = made.fetch(["ledger"], ["throughput"], limit=1)

    assert papers[0]["Authors"] == "Lovelace, Ada; Berg, Jan van der; The Ledger Consortium"


def test_openalex_reads_the_display_names_it_already_sends(monkeypatch):
    made = connector(OpenAlexConnector, monkeypatch, payload={"results": [OPENALEX_ITEM]})

    papers = made.fetch(["ledger"], ["throughput"], limit=1)

    assert papers[0]["Authors"] == "Ada Lovelace; Jan van der Berg"


def test_arxiv_reads_the_author_element_it_already_parses(monkeypatch):
    """O nome vem partido pela indentação, como o título e o abstract vêm."""
    made = connector(ArxivConnector, monkeypatch, text=ARXIV_ATOM)

    papers = made.fetch(["ledger"], ["throughput"], limit=1)

    assert papers[0]["Authors"] == "Ada Lovelace; Jan van der Berg"


def test_semantic_scholar_asks_for_the_field_before_reading_it(monkeypatch):
    """Sem `authors` na lista de `fields`, a API não devolve o campo.

    Ler um campo que não foi pedido é uma linha que passa em todos os testes com
    resposta simulada e devolve nada contra a API.
    """
    payload = {"data": [{"title": "Ledgers at scale", "authors": [{"name": "Ada Lovelace"}]}]}
    made = connector(SemanticScholarConnector, monkeypatch, payload=payload)

    papers = made.fetch(["ledger"], ["throughput"], limit=1)

    requested = made.calls[0][1]["fields"].split(",")
    assert "authors" in requested, f"the request never asked for authors: {requested}"
    assert papers[0]["Authors"] == "Ada Lovelace"


@pytest.mark.parametrize("listing", [None, "Ada Lovelace", 7])
def test_a_source_that_sends_something_other_than_a_list_yields_no_authors(listing):
    """Um campo com a forma errada não pode derrubar a coleta inteira."""
    from academic_hunter.core.models.authors import listed_authors, openalex_authors

    assert listed_authors(listing) == ""
    assert openalex_authors(listing) == ""


def test_a_name_that_arrives_twice_is_written_once():
    from academic_hunter.core.models.authors import crossref_authors

    assert crossref_authors(
        [{"family": "Lovelace", "given": "Ada"}, {"family": "lovelace", "given": "ada"}]
    ) == "Lovelace, Ada"


def test_a_mononym_keeps_the_half_it_has():
    from academic_hunter.core.models.authors import format_name

    assert format_name("Plato", None) == "Plato"
    assert format_name(None, "Ada") == "Ada"
    assert format_name("Berg", "Jan van der") == "Berg, Jan van der"


TRUNCATED = "Lovelace, Ada"
COMPLETE = "Lovelace, Ada; Berg, Jan van der; Hopper, Grace"


@pytest.mark.parametrize("old,new", [(TRUNCATED, COMPLETE), (COMPLETE, TRUNCATED)])
def test_the_longer_list_wins_whichever_copy_arrives_first(old, new):
    """Uma fonte que devolve três de nove nomes não discorda da que devolve nove."""
    assert strategy_authors(old, new) == COMPLETE


def test_two_equally_long_lists_settle_the_same_way_round():
    """Arbitrário, mas o mesmo lado em cada run — é o que torna dois runs comparáveis."""
    first = "Ada Lovelace; Grace Hopper"
    second = "Lovelace, Ada; Hopper, Grace"

    assert strategy_authors(first, second) == strategy_authors(second, first)


def test_an_absent_list_never_erases_a_present_one():
    assert strategy_authors("", COMPLETE) == COMPLETE
    assert strategy_authors(COMPLETE, "") == COMPLETE
    assert strategy_authors("", "") == ""


CONFIG = {
    "settings": {"min_relevance_score": 0.0, "start_year": 2021, "title_multiplier": 1.5},
    "anchors": {"cat": ["ledger"]},
    "technical_strings": {},
    "technical_weights": {"ledger": 1.0},
}


def processor(tmp_path):
    from academic_hunter.core.infra import HunterConfig, SearchState
    from academic_hunter.core.nlp import AcademicScorer
    from academic_hunter.core.screening.processor import PaperProcessor

    path = tmp_path / "config.json"
    path.write_text(json.dumps(CONFIG))
    config = HunterConfig(config_path=str(path))
    scorer = AcademicScorer(
        config.anchors, config.tech_strings, config.tech_weights,
        config.context_rules, config.settings,
    )
    return PaperProcessor(
        state=SearchState(), scorer=scorer, config=config,
        connectors={}, lock=threading.RLock(),
    )


def record(**overrides):
    return {
        "Title": "A study of ledger systems",
        "Authors": COMPLETE,
        "Abstract": "We study ledger throughput.",
        "Year": "2024",
        "Source": "Crossref",
        "Citations": 0,
        "Type": "journal-article",
        "Venue": "Journal of Ledgers",
        "URL": "https://example.org/ledger",
        "DOI": "10.1234/ledger",
        **overrides,
    }


def stored_one(proc):
    return next(iter(proc.state.consolidated_results.values()))


def test_the_registered_paper_carries_the_authors_the_connector_read(tmp_path):
    """`register_new_paper` constrói um `Paper` novo a partir de uma lista fixa.

    Um campo que o connector lê e essa lista não copia é descartado em silêncio:
    o `Paper` tem a chave, com o valor por omissão, e nada no run se queixa.
    """
    proc = processor(tmp_path)

    proc.process(paper=record(), anchor_cat="cat", tech_cat="cat",
                 anchor_list=["ledger"], tech_list=[])

    assert stored_one(proc)["Authors"] == COMPLETE


def test_two_copies_of_one_study_leave_the_complete_author_list(tmp_path):
    """A cópia que chega depois traz mais nomes e o merge tem de os guardar."""
    proc = processor(tmp_path)

    proc.process(paper=record(Source="OpenAlex", Authors=TRUNCATED),
                 anchor_cat="cat", tech_cat="cat", anchor_list=["ledger"], tech_list=[])
    proc.process(paper=record(Source="Crossref"), anchor_cat="cat", tech_cat="cat",
                 anchor_list=["ledger"], tech_list=[])

    assert stored_one(proc)["Authors"] == COMPLETE


def test_two_copies_of_one_study_leave_the_complete_author_list_in_either_order(tmp_path):
    proc = processor(tmp_path)

    proc.process(paper=record(Source="Crossref"), anchor_cat="cat", tech_cat="cat",
                 anchor_list=["ledger"], tech_list=[])
    proc.process(paper=record(Source="OpenAlex", Authors=TRUNCATED),
                 anchor_cat="cat", tech_cat="cat", anchor_list=["ledger"], tech_list=[])

    assert stored_one(proc)["Authors"] == COMPLETE


def exported(tmp_path, exporter, papers, stats=None):
    context = ExportContext(
        papers=papers,
        stats=stats if stats is not None else {"identified": {}, "exclusions_by_source": {}},
        settings={"min_relevance_score": 3.5, "start_year": 2021},
        query_history=[],
        anchors={},
        tech_strings={},
        timestamp="test_run",
        output_dir=tmp_path,
    )
    exporter.export(context)
    return next(f for f in Path(tmp_path).rglob("*") if f.suffix in (".bib", ".ris", ".csv", ".md"))


def test_bibtex_joins_the_authors_with_the_word_bibtex_reads(tmp_path):
    """`and` é o separador do BibTeX; `;` é o do campo guardado, e não o substitui."""
    content = exported(tmp_path, BibtexExporter(), [Paper(record())]).read_text(encoding="utf-8")

    assert "author = {Lovelace, Ada and Berg, Jan van der and Hopper, Grace}," in content


def test_bibtex_escapes_the_author_field_like_every_other(tmp_path):
    """Um `&` num organismo que assina o artigo pára a compilação em modo texto."""
    paper = Paper(record(Authors="R&D Consortium"))
    content = exported(tmp_path, BibtexExporter(), [paper]).read_text(encoding="utf-8")

    assert r"author = {R\&D Consortium}," in content


def test_bibtex_keeps_the_field_order_the_reader_expects(tmp_path):
    content = exported(tmp_path, BibtexExporter(), [Paper(record())]).read_text(encoding="utf-8")

    fields = [
        line.split(" = ")[0].strip()
        for line in content.splitlines()
        if " = " in line and not line.startswith("@")
    ]
    assert fields == ["title", "author", "journal", "year", "url", "doi", "abstract"]


def test_an_authorless_record_gets_no_field_at_all(tmp_path):
    """`author = {}` compila para uma referência com um branco onde vai o nome.

    Isso lê-se como falha de composição, não como o dado que falta — pior do que
    a ausência que se está a admitir.
    """
    content = exported(tmp_path, BibtexExporter(), [Paper(record(Authors=""))]).read_text(encoding="utf-8")

    assert "author" not in content


def test_ris_writes_one_line_per_author(tmp_path):
    """Um `AU  - ` com três nomes dentro é um autor chamado «Ada, Berg e Grace»."""
    content = exported(tmp_path, RisExporter(), [Paper(record())]).read_text(encoding="utf-8")

    lines = [line for line in content.splitlines() if line.startswith("AU  - ")]
    assert lines == [
        "AU  - Lovelace, Ada",
        "AU  - Berg, Jan van der",
        "AU  - Hopper, Grace",
    ]


def test_ris_writes_no_author_line_when_there_are_no_authors(tmp_path):
    content = exported(tmp_path, RisExporter(), [Paper(record(Authors=""))]).read_text(encoding="utf-8")

    assert "AU  - " not in content


def test_the_csv_carries_the_column(tmp_path):
    """É a coluna que o revisor lê; o `.bib` é para a bibliografia final."""
    import csv as csv_module

    csv_file = exported(tmp_path, CsvExporter(), [Paper(record())])
    with open(csv_file, newline="", encoding="utf-8") as f:
        rows = list(csv_module.DictReader(f))

    assert rows[0]["Authors"] == COMPLETE


def test_the_report_names_the_authors(tmp_path):
    stats = {"identified": {}, "exclusions_by_source": {}, "included_final": 1}

    content = exported(
        tmp_path, MarkdownEliteExporter(), [Paper(record())], stats=stats
    ).read_text(encoding="utf-8")

    assert f"- **Authors:** {COMPLETE}" in content


def test_the_report_omits_the_line_rather_than_printing_an_empty_one(tmp_path):
    stats = {"identified": {}, "exclusions_by_source": {}, "included_final": 1}

    content = exported(
        tmp_path, MarkdownEliteExporter(), [Paper(record(Authors=""))], stats=stats
    ).read_text(encoding="utf-8")

    assert "**Authors:**" not in content


CORE_RECORD = record(Source="CORE", Authors="", Venue="Unknown Venue")


def test_a_source_that_publishes_no_authors_leaves_the_field_empty(tmp_path):
    """CORE e DOAJ não oferecem autoria.

    Um paper cuja única cópia venha de um deles continua sem autores, e o `.bib`
    continua sem `author`. É o limite da correção, e fica escrito em vez de
    subentendido.
    """
    proc = processor(tmp_path)

    proc.process(paper=dict(CORE_RECORD), anchor_cat="cat", tech_cat="cat",
                 anchor_list=["ledger"], tech_list=[])

    assert stored_one(proc)["Authors"] == ""

    content = exported(tmp_path, BibtexExporter(), [stored_one(proc)]).read_text(encoding="utf-8")
    assert "author" not in content
