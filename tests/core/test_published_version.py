"""A preprint's published version, found by search and accepted by rule.

Medido no run entregue: 109 dos 310 papers são preprints, e o relatório nomeia a
venue e o ano do próprio preprint para um trabalho publicado noutro sítio — um
posting arXiv de 2021 a fazer as vezes da comunicação em conferência de que é o
preprint. O autor encontrou-o à mão, e a correcção tem de passar por uma busca
bibliográfica, que é a única coisa que sabe onde é que o trabalho foi publicado.

Dois limites ficam fixados aqui em vez de ficarem implícitos. O resultado é
``Likely`` e nunca ``Yes``: um registo igual prova que a versão publicada existe,
não que alguém a reviu. E o ``DOI`` do preprint não é substituído pelo da versão
publicada — o ``DOI`` é a chave de identidade que liga o pool, a página de
julgamento e a distribuição de pontuações, e movê-la depois de o pool ter sido
construído perderia os julgamentos que a passagem do DOI existe para proteger.
"""

import threading
from pathlib import Path

import pytest

from academic_hunter.core.infra import SearchState
from academic_hunter.core.models import Paper
from academic_hunter.core.models.published_version import (
    author_overlap,
    best_match,
    is_preprint,
    match,
    normalize_title,
    surname,
)
from academic_hunter.core.pipeline.enricher import MetadataEnricher
from academic_hunter.plugins.connectors.crossref import CrossrefConnector
from academic_hunter.plugins.exporters.base import ExportContext
from academic_hunter.plugins.exporters.prisma import PrismaExporter

TITLE = "SmartLLM: Smart Contract Auditing Using Custom Generative AI"
EMPTY = "This is not the paper you are looking for"

PUBLISHED_DOI = "10.1145/3576915.3623202"

CANDIDATE = {
    "DOI": PUBLISHED_DOI,
    "Title": TITLE,
    "Authors": "Lovelace, Ada; Berg, Jan van der",
    "Type": "proceedings-article",
    "Venue": "Proceedings of the ACM SIGSAC Conference on Computer and Communications Security",
    "Year": 2025,
}


class FakeCrossref:
    """A connector that answers with the candidate list it was built with."""

    SOURCE_NAME = "Crossref"
    resolve_priority = 2

    def __init__(self, candidates=None, raises=False):
        self.candidates = [dict(c) for c in (candidates or [])]
        self.raises = raises
        self.asked = []

    def find_published_version(self, title, authors=""):
        self.asked.append((title, authors))
        if self.raises:
            raise RuntimeError("Crossref is down")
        return {"title": title, "candidates": [dict(c) for c in self.candidates]}


def preprint(**overrides):
    return Paper({
        "Title": TITLE,
        "Authors": "Ada Lovelace; Jan van der Berg",
        "Abstract": "We audit smart contracts with a language model.",
        "URL": "http://arxiv.org/abs/2502.13167v1",
        "Source": "ArXiv",
        "Peer_Reviewed": "No (Preprint)",
        "Venue": "ArXiv",
        "Year": "2025",
        "DOI": "10.48550/arxiv.2502.13167",
        **overrides,
    })


def enricher(papers, connector=None, settings=None):
    state = SearchState()
    state.consolidated_results = {f"slug-{i}": paper for i, paper in enumerate(papers)}
    return MetadataEnricher(
        connectors={"crossref": connector} if connector else {},
        state=state,
        lock=threading.RLock(),
        settings=settings if settings is not None else {"start_year": 2021},
    )


@pytest.mark.parametrize(
    "left,right",
    [
        (TITLE, TITLE.lower()),
        (TITLE, "SmartLLM — smart contract auditing using custom generative AI"),
        ("A study of ledger systems", "A  study of   ledger systems"),
        ("Blockchain: a survey", "Blockchain - A Survey"),
    ],
)
def test_titles_that_name_the_same_work_normalise_alike(left, right):
    """A pontuação e as maiúsculas diferem entre o preprint e a versão publicada."""
    assert normalize_title(left) == normalize_title(right)


def test_titles_that_name_different_works_do_not():
    assert normalize_title(TITLE) != normalize_title(EMPTY)


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Lovelace, Ada", "lovelace"),
        ("Ada Lovelace", "lovelace"),
        ("Berg, Jan van der", "berg"),
        ("Jan van der Berg", "berg"),
        ("", ""),
        ("   ", ""),
    ],
)
def test_a_family_name_is_read_from_either_spelling(name, expected):
    """Só se divide onde a API já dividiu; o resto é reduzido sem inventar."""
    assert surname(name) == expected


def test_one_shared_surname_is_enough():
    """Listas de autores são reordenadas e acrescentadas entre as duas versões."""
    assert author_overlap("Ada Lovelace; Jan van der Berg", "Berg, Jan van der; Hopper, Grace")


def test_no_shared_surname_is_a_disagreement():
    assert not author_overlap("Ada Lovelace", "Hopper, Grace")


def test_a_candidate_that_repeats_the_title_and_the_surname_is_accepted():
    assert match(preprint(), CANDIDATE) == (True, "title_and_authors")


def test_a_candidate_that_disagrees_on_the_title_is_refused():
    assert match(preprint(), {**CANDIDATE, "Title": EMPTY}) == (False, "title")


def test_a_candidate_that_shares_no_surname_is_refused():
    """O título sozinho encontra o trabalho errado com frequência suficiente para importar."""
    assert match(preprint(), {**CANDIDATE, "Authors": "Hopper, Grace"}) == (False, "authors")


def test_a_candidate_that_is_itself_a_preprint_is_refused():
    """Promover o próprio registo do preprint não promove nada."""
    assert match(preprint(), {**CANDIDATE, "Type": "posted-content"}) == (False, "is_a_preprint")


def test_a_candidate_that_only_repeats_the_doi_is_refused():
    same = {**CANDIDATE, "DOI": "10.48550/arxiv.2502.13167"}
    assert match(preprint(), same) == (False, "same_doi")


def test_a_candidate_without_a_doi_is_refused():
    assert match(preprint(), {**CANDIDATE, "DOI": ""}) == (False, "no_doi")


def test_a_title_match_with_no_authors_to_compare_is_accepted_and_named():
    """CORE e DOAJ não publicam autoria; recusar por isso seria recusar pela fonte errada.

    O que a aceitação não pode é ficar indistinguível de uma confirmada, e é por
    isso que a razão é ``title_only``.
    """
    bare = preprint(Authors="")
    assert match(bare, {**CANDIDATE, "Authors": ""}) == (True, "title_only")
    assert match(bare, CANDIDATE) == (True, "title_only")


def test_a_candidate_with_an_empty_title_is_refused():
    assert match(preprint(), {**CANDIDATE, "Title": ""}) == (False, "no_title")


def test_the_first_acceptable_candidate_wins():
    refused = {**CANDIDATE, "Title": EMPTY}
    accepted = {**CANDIDATE, "DOI": "10.5555/second"}
    assert best_match(preprint(), [refused, accepted])[0]["DOI"] == "10.5555/second"


def test_a_candidate_list_that_is_not_a_list_is_no_answer():
    assert best_match(preprint(), None) == ({}, "")
    assert best_match(preprint(), "an error message") == ({}, "")


def test_only_a_preprint_with_an_identifier_is_worth_searching_for():
    assert is_preprint(preprint(), "2502.13167")
    assert not is_preprint(preprint(), "")
    assert not is_preprint(preprint(Peer_Reviewed="Yes"), "2502.13167")


def test_a_matching_record_promotes_the_preprint_to_likely():
    paper = preprint()
    connector = FakeCrossref([CANDIDATE])

    summary = enricher([paper], connector).resolve_published_versions()

    assert paper["Peer_Reviewed"] == "Likely"
    assert paper["Venue"] == CANDIDATE["Venue"]
    assert paper["Year"] == 2025
    assert summary["promoted"] == 1
    assert connector.asked == [(TITLE, "Ada Lovelace; Jan van der Berg")]


def test_never_promotes_to_yes():
    """Um registo igual prova que a versão publicada existe, não que foi revista."""
    paper = preprint()

    enricher([paper], FakeCrossref([CANDIDATE])).resolve_published_versions()

    assert paper["Peer_Reviewed"] == "Likely"


def test_the_preprints_own_doi_is_never_replaced():
    """O DOI é a chave de identidade do pool, da página e da distribuição.

    Substituí-lo por um DOI de editora moveria essa chave uma segunda vez, depois
    de o pool ter sido construído, e perderia os mesmos julgamentos que a
    passagem do DOI do lote Q existe para proteger. O DOI publicado fica ao lado.
    """
    paper = preprint()

    summary = enricher([paper], FakeCrossref([CANDIDATE])).resolve_published_versions()

    assert paper["DOI"] == "10.48550/arxiv.2502.13167"
    assert summary["promotions"][0]["published_doi"] == PUBLISHED_DOI


def test_a_record_that_disagrees_on_the_title_leaves_the_paper_alone():
    paper = preprint()
    before = dict(paper)

    summary = enricher([paper], FakeCrossref([{**CANDIDATE, "Title": EMPTY}])).resolve_published_versions()

    assert dict(paper) == before
    assert summary["unmatched"] == 1
    assert summary["promoted"] == 0


def test_a_record_with_no_shared_surname_leaves_the_paper_alone():
    paper = preprint()
    before = dict(paper)

    summary = enricher(
        [paper], FakeCrossref([{**CANDIDATE, "Authors": "Hopper, Grace"}])
    ).resolve_published_versions()

    assert dict(paper) == before
    assert summary["unmatched"] == 1


def test_a_paper_that_is_already_published_is_never_asked_about():
    """Uma segunda pergunta cuja resposta só podia sobrepor-se a uma melhor."""
    published = preprint(Peer_Reviewed="Yes", Venue="IEEE S&P", Year="2025")
    connector = FakeCrossref([CANDIDATE])

    summary = enricher([published], connector).resolve_published_versions()

    assert connector.asked == []
    assert published["Venue"] == "IEEE S&P"
    assert summary["asked"] == 0


def test_a_preprint_with_no_arxiv_id_is_counted_rather_than_asked():
    """Sem identificador não há preprint *de quê* para procurar a versão publicada."""
    paper = preprint(URL="https://core.ac.uk/works/391546543")
    connector = FakeCrossref([CANDIDATE])

    summary = enricher([paper], connector).resolve_published_versions()

    assert connector.asked == []
    assert summary["without_identifier"] == 1
    assert summary["preprints"] == 1
    assert paper["Peer_Reviewed"] == "No (Preprint)"


def test_a_lookup_that_fails_leaves_the_paper_as_it_was():
    paper = preprint()
    before = dict(paper)

    summary = enricher([paper], FakeCrossref(raises=True)).resolve_published_versions()

    assert dict(paper) == before
    assert summary["failed"] == 1
    assert summary["promoted"] == 0


def test_the_summary_says_how_many_matches_had_the_second_proof():
    papers = [
        preprint(),
        preprint(Title="A second preprint", Authors=""),
    ]
    connector = FakeCrossref([
        CANDIDATE,
        {**CANDIDATE, "DOI": "10.5555/second", "Title": "A second preprint", "Authors": ""},
    ])

    summary = enricher(papers, connector).resolve_published_versions()

    assert summary["promoted"] == 2
    assert summary["promoted_on_title_alone"] == 1
    assert [entry["match"] for entry in summary["promotions"]] == [
        "title_and_authors",
        "title_only",
    ]


def test_a_promotion_dated_before_the_start_year_is_reported():
    """O filtro temporal do run correu sobre o ano do preprint, não sobre este.

    A versão publicada pode ser mais antiga do que o corte que o run aplicou, e
    nesse caso o conjunto exportado passa a ir mais atrás do que o próprio run
    declara. Isso é um efeito visível, não um detalhe.
    """
    paper = preprint()

    summary = enricher(
        [paper], FakeCrossref([{**CANDIDATE, "Year": 2016}]), settings={"start_year": 2021}
    ).resolve_published_versions()

    assert paper["Year"] == 2016
    assert summary["before_start_year"] == [
        {"title": TITLE, "year": 2016, "doi": PUBLISHED_DOI}
    ]


def test_a_promotion_inside_the_window_is_not_reported_as_an_anomaly():
    summary = enricher(
        [preprint()], FakeCrossref([CANDIDATE]), settings={"start_year": 2021}
    ).resolve_published_versions()

    assert summary["before_start_year"] == []


def test_a_candidate_with_no_year_still_promotes_on_the_venue():
    paper = preprint()
    candidate = {**CANDIDATE, "Year": "N/A"}

    summary = enricher([paper], FakeCrossref([candidate])).resolve_published_versions()

    assert summary["promoted"] == 1
    assert paper["Venue"] == CANDIDATE["Venue"]
    assert paper["Year"] == "2025", "um ano ausente não é um ano desconhecido"


def test_the_search_can_be_switched_off_by_configuration():
    for settings in (
        {"start_year": 2021, "published_version": False},
        {"start_year": 2021, "published_version": {"enabled": False}},
    ):
        paper = preprint()
        connector = FakeCrossref([CANDIDATE])

        assert enricher([paper], connector, settings=settings).resolve_published_versions() == {}
        assert connector.asked == []
        assert paper["Peer_Reviewed"] == "No (Preprint)"


def test_a_connector_that_cannot_search_is_inert():
    """Sem capacidade de busca a passagem não corre, e diz porquê em vez de contar zero."""

    class OnlyResolves:
        SOURCE_NAME = "Crossref"
        resolve_priority = 2

        def resolve_metadata_by_doi(self, doi):
            return {}

    paper = preprint()
    assert enricher([paper], OnlyResolves()).resolve_published_versions() == {}
    assert paper["Peer_Reviewed"] == "No (Preprint)"


def test_the_highest_priority_connector_that_can_search_is_the_one_asked():
    """A escolha não é a ordem do dicionário, que é a ordem de registo e não diz nada.

    O ``resolve_priority`` já é a afirmação do repositório sobre que fonte
    preferir — é o que ordena as consultas de abstract e de citações — e é ele
    que decide aqui em vez de uma segunda ordenação inventada neste ponto.
    """
    best = FakeCrossref([CANDIDATE])
    best.SOURCE_NAME = "Zeta"
    best.resolve_priority = 5

    other = FakeCrossref([])
    other.SOURCE_NAME = "Alpha"
    other.resolve_priority = 4

    state = SearchState()
    state.consolidated_results = {"slug": preprint()}
    made = MetadataEnricher(
        connectors={"alpha": other, "zeta": best},
        state=state,
        lock=threading.RLock(),
        settings={"start_year": 2021},
    )

    made.resolve_published_versions()

    assert best.asked and not other.asked


def test_a_connector_that_can_search_without_declaring_a_priority_is_still_asked():
    """``find_published_version`` é opt-in, logo tê-lo é a permissão para ser
    perguntado e a prioridade só ordena — aqui, para o fim da lista.

    Descartar por falta de número seria silencioso: a passagem diria que nenhum
    candidato foi encontrado, quando não chegou a perguntar a ninguém.
    """
    connector = FakeCrossref([CANDIDATE])
    connector.SOURCE_NAME = "Unranked"
    connector.resolve_priority = 0
    paper = preprint()

    summary = enricher([paper], connector).resolve_published_versions()

    assert connector.asked, "a fonte que sabe responder nunca foi consultada"
    assert summary["promoted"] == 1
    assert paper["Peer_Reviewed"] == "Likely"


CROSSREF_ITEM = {
    "DOI": PUBLISHED_DOI,
    "title": [TITLE],
    "author": [
        {"family": "Lovelace", "given": "Ada"},
        {"family": "Berg", "given": "Jan van der"},
    ],
    "type": "proceedings-article",
    "container-title": ["Proceedings of the ACM SIGSAC Conference on Computer and Communications Security"],
    "published-print": {"date-parts": [[2025, 10, 14]]},
}


def crossref(monkeypatch, payload, **settings):
    connector = CrossrefConnector(
        settings={"user_email": "test@example.com", **settings},
        cache=None,
        query_history=[],
        lock=threading.RLock(),
        semaphore=threading.Semaphore(1),
    )
    calls = []

    def fake_request(url, params=None, timeout=20, max_retries=2):
        calls.append((url, params))
        return payload

    monkeypatch.setattr(connector, "_make_request", fake_request)
    return connector, calls


def test_the_search_asks_crossref_by_title_and_reads_the_candidates(monkeypatch):
    connector, calls = crossref(monkeypatch, {"message": {"items": [CROSSREF_ITEM]}})

    answer = connector.find_published_version(TITLE, "Ada Lovelace")

    assert calls == [(
        "https://api.crossref.org/works",
        {"query.bibliographic": TITLE, "rows": 5, "mailto": "test@example.com"},
    )]
    assert answer["candidates"] == [{
        "DOI": PUBLISHED_DOI,
        "Title": TITLE,
        "Authors": "Lovelace, Ada; Berg, Jan van der",
        "Type": "proceedings-article",
        "Venue": "Proceedings of the ACM SIGSAC Conference on Computer and Communications Security",
        "Year": 2025,
    }]


def test_the_search_does_not_run_on_an_empty_title(monkeypatch):
    connector, calls = crossref(monkeypatch, {"message": {"items": [CROSSREF_ITEM]}})

    assert connector.find_published_version("", "")["candidates"] == []
    assert connector.find_published_version("   ", "")["candidates"] == []
    assert calls == []


def test_a_response_that_is_not_a_work_list_yields_no_candidates(monkeypatch):
    for payload in (None, {}, {"message": {}}, {"message": {"items": None}}, "an error"):
        connector, _ = crossref(monkeypatch, payload)
        assert connector.find_published_version(TITLE)["candidates"] == []


def test_one_malformed_item_does_not_hide_the_others(monkeypatch):
    payload = {"message": {"items": ["a string", CROSSREF_ITEM]}}
    connector, _ = crossref(monkeypatch, payload)

    assert len(connector.find_published_version(TITLE)["candidates"]) == 1


@pytest.mark.parametrize(
    "item,expected",
    [
        ({"published-print": {"date-parts": [[2025, 10]]},
          "published-online": {"date-parts": [[2024, 3]]}}, 2025),
        ({"published-online": {"date-parts": [[2024, 3]]},
          "issued": {"date-parts": [[2023, 1]]}}, 2024),
        ({"issued": {"date-parts": [[2023, 1]]},
          "created": {"date-parts": [[2020, 1, 1]]}}, 2023),
        ({"created": {"date-parts": [[2020, 1, 1]]}}, 2020),
        ({}, "N/A"),
        ({"issued": {"date-parts": []}}, "N/A"),
    ],
)
def test_the_year_comes_from_the_first_date_the_record_has(item, expected):
    """A mesma ordem para a busca que encontrou o paper e para a que procura a versão."""
    assert CrossrefConnector.work_year(item) == expected


PROMOTION_SUMMARY = {
    "preprints": 3,
    "asked": 2,
    "failed": 0,
    "promoted": 1,
    "unmatched": 1,
    "promoted_on_title_alone": 0,
    "without_identifier": 1,
    "before_start_year": [],
    "promotions": [{
        "title": TITLE,
        "doi": "10.48550/arxiv.2502.13167",
        "published_doi": PUBLISHED_DOI,
        "venue": CANDIDATE["Venue"],
        "year": 2025,
        "match": "title_and_authors",
    }],
}


def prisma_report(tmp_path, published):
    exporter = PrismaExporter()
    exporter.export(ExportContext(
        papers=[{
            "Title": TITLE,
            "Citations": 3,
            "Citations_Source": "crossref",
            "Relevance_Score": 5.0,
            "Year": 2025,
            "Venue": CANDIDATE["Venue"],
            "Peer_Reviewed": "Likely",
            "Source": "ArXiv",
            "DOI": "10.48550/arxiv.2502.13167",
            "Anchor_Category": "Blockchain",
            "URL": "https://arxiv.org/abs/2502.13167",
        }],
        stats={
            "identified": {"arxiv": 1},
            "exclusions_by_source": {},
            "included_final": 1,
            "published_version": published,
        },
        settings={"start_year": 2021, "min_relevance_score": 3.5},
        query_history=[],
        anchors={"Blockchain": ["blockchain"]},
        tech_strings={"Core": ["ledger"]},
        timestamp="test_published_version",
        output_dir=tmp_path,
    ))
    return sorted(Path(tmp_path).rglob("*.md"))[0].read_text(encoding="utf-8")


def test_the_report_names_what_was_promoted_and_where_to(tmp_path):
    """Quem lê tem de poder ver o que mudou, e contra que registo."""
    content = prisma_report(tmp_path, PROMOTION_SUMMARY)

    assert CANDIDATE["Venue"] in content
    assert PUBLISHED_DOI in content
    assert "Published Versions Found:** 1" in content


def test_the_report_distinguishes_a_confirmed_match_from_a_title_only_one(tmp_path):
    summary = {**PROMOTION_SUMMARY, "promoted_on_title_alone": 1,
               "promotions": [{**PROMOTION_SUMMARY["promotions"][0], "match": "title_only"}]}

    content = prisma_report(tmp_path, summary)

    assert "on the title alone" in content


def test_a_run_that_searched_for_nothing_does_not_claim_a_section(tmp_path):
    """Uma secção a zero sobre uma passagem que não correu lê-se como uma medição."""
    content = prisma_report(tmp_path, {})

    assert "Published Versions Found" not in content
    assert "Preprints Examined" not in content
