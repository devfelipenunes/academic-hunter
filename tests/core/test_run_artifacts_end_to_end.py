"""Um run de verdade escreve os três artefatos — e o que entrou é o que saiu.

O e2e do PRISMA para no diagrama. Do diagrama para a frente (CSV, BibTeX, RIS)
não havia teste nenhum, e nenhum dos papers dele tem DOI — então a identidade
que o projeto declara canônica (`normalize_doi`) ficava inteiramente de fora do
único teste que roda o pipeline de ponta a ponta.

Os DOIs aqui entram na forma suja (`https://doi.org/...`, maiúsculas) de
propósito: se as camadas discordarem sobre a forma canônica, o mesmo trabalho
vira dois papers e a contagem do PRISMA deixa de fechar.
"""

import csv
import json
import re

import pytest

from academic_hunter import AcademicHunter

CONFIG = {
    "settings": {"min_relevance_score": 0.0, "start_year": 2024},
    "anchors": {"test": ["blockchain"]},
    "technical_strings": {"test": ["latency", "consensus"]},
    "technical_weights": {"blockchain": 5.0, "latency": 3.0, "consensus": 2.0},
}

CONNECTORS = (
    "fetch_arxiv", "fetch_crossref", "fetch_semantic_scholar", "fetch_openalex",
    "fetch_core_ac", "fetch_doaj",
)

WITH_DOI = [
    ("Blockchain latency in payment rails", "https://doi.org/10.1234/ALPHA"),
    ("Blockchain consensus protocols", "http://dx.doi.org/10.1234/Beta"),
    ("A blockchain survey", "doi:10.1234/GAMMA"),
]


def _papers():
    return [
        {
            "Title": title,
            "Abstract": "Blockchain latency and consensus trade-offs.",
            "Year": "2024",
            "URL": f"http://example.com/{i}",
            "Source": "Mock",
            "Citations": 10 - i,
            "Type": "article",
            "Venue": "Mock Venue",
            "DOI": doi,
        }
        for i, (title, doi) in enumerate(WITH_DOI)
    ]


def _silence_connectors(hunter, monkeypatch, published=None):
    """No connector-level lookup reaches the network from this file.

    Stubbing ``fetch_arxiv`` and its siblings leaves the connectors themselves
    untouched, and the pipeline asks them twice more once the search threads have
    joined: for the citations no source reported, and for the published version of
    each preprint. Both are real HTTP calls, so without this the suite would
    measure whichever API happened to answer — and would fail on a machine with
    no network for a reason that has nothing to do with the artifacts.
    """
    for connector in hunter.connectors.values():
        if hasattr(connector, "fetch_citations_by_dois"):
            monkeypatch.setattr(connector, "fetch_citations_by_dois", lambda dois, **k: {})
        if hasattr(connector, "resolve_metadata_by_doi"):
            monkeypatch.setattr(connector, "resolve_metadata_by_doi", lambda doi: {})
        if hasattr(connector, "find_published_version"):
            candidates = list(published or [])
            monkeypatch.setattr(
                connector,
                "find_published_version",
                lambda title, authors="", _c=candidates: {"title": title, "candidates": list(_c)},
            )


def _run(tmp_path, monkeypatch, papers, published=None):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(CONFIG), encoding="utf-8")
    hunter = AcademicHunter(config_path=str(config_path), output_dir=str(tmp_path))
    _silence_connectors(hunter, monkeypatch, published)

    for name in CONNECTORS:
        monkeypatch.setattr(
            AcademicHunter, name, lambda *a, **k: [p.copy() for p in papers]
        )
    return hunter, hunter.run(limit_per_source=1)


@pytest.fixture
def artifacts(tmp_path, monkeypatch):
    hunter, returned = _run(tmp_path, monkeypatch, _papers())
    found = {
        ext: sorted(tmp_path.rglob(f"*.{ext}"))
        for ext in ("csv", "bib", "ris", "md")
    }
    assert found["csv"] and found["bib"] and found["ris"], f"missing artifacts: {found}"
    return hunter, found, returned


def _dois_in_csv(path) -> set:
    with open(path, encoding="utf-8") as handle:
        return {row["DOI"].strip() for row in csv.DictReader(handle) if row["DOI"].strip()}


def _dois_in_bib(text: str) -> set:
    return {m.strip() for m in re.findall(r"^\s*doi = \{([^}]*)\},", text, re.M) if m.strip()}


def _dois_in_ris(text: str) -> set:
    return {m.strip() for m in re.findall(r"^DO {2}- (.+)$", text, re.M) if m.strip()}


def test_the_canonical_doi_reaches_every_artifact(artifacts):
    """One work, one identity — from the connector to the bibliography.

    Compared as field *values*, not as substrings: `"10.1234/alpha" in text` is
    also true of `"https://10.1234/alpha"`, so a layer that failed to strip the
    prefix would pass a substring check while shipping a DOI no other layer
    recognises — which is how one work became two papers.
    """
    _, found, _ = artifacts
    expected = {"10.1234/alpha", "10.1234/beta", "10.1234/gamma"}

    got = {
        "csv": _dois_in_csv(found["csv"][0]),
        "bib": _dois_in_bib(found["bib"][0].read_text(encoding="utf-8")),
        "ris": _dois_in_ris(found["ris"][0].read_text(encoding="utf-8")),
    }

    for artifact, values in got.items():
        assert values == expected, f"{artifact} carries {sorted(values)}"


def test_the_artifacts_agree_on_how_many_papers_came_out(artifacts):
    """The count in the stats, the CSV rows and the .bib entries are one number."""
    hunter, found, _ = artifacts

    with open(found["csv"][0], encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle)]
    entries = re.findall(r"^@article\{", found["bib"][0].read_text(encoding="utf-8"), re.M)

    assert len(rows) == len(entries), f"CSV has {len(rows)} rows, .bib has {len(entries)}"
    assert len(rows) == hunter.stats["included_final"], (
        f"{len(rows)} papers were exported but the stats report "
        f"{hunter.stats['included_final']} included"
    )


PREPRINT = {
    "Title": "Blockchain latency at the edge",
    "Authors": "Ada Lovelace",
    "Abstract": "Blockchain latency and consensus on a public ledger.",
    "Year": "2024",
    "URL": "http://arxiv.org/abs/2401.00001v2",
    "Source": "ArXiv",
    "Citations": 0,
    "Type": "preprint",
    "Venue": "ArXiv",
    "Peer_Reviewed": "No (Preprint)",
}

PUBLISHED_VERSION = {
    "DOI": "10.1145/3576915.3623202",
    "Title": PREPRINT["Title"],
    "Authors": "Lovelace, Ada; Hopper, Grace",
    "Type": "proceedings-article",
    "Venue": "Proceedings of the ACM SIGSAC Conference on Computer and Communications Security",
    "Year": "2024",
}


@pytest.fixture
def preprint_run(tmp_path, monkeypatch):
    papers = _papers() + [dict(PREPRINT)]
    hunter, _ = _run(tmp_path, monkeypatch, papers)
    csv_path = sorted(tmp_path.rglob("*.csv"))[0]
    distribution = sorted(tmp_path.rglob("score_distribution_*.json"))[0]
    return hunter, csv_path, distribution


def _row_for(path, title):
    with open(path, encoding="utf-8") as handle:
        return next(row for row in csv.DictReader(handle) if row["Title"] == title)


def test_a_preprint_that_arrives_without_a_doi_leaves_with_one(preprint_run):
    """O conector do arXiv não publica DOI, e o URL nomeia o trabalho.

    109 dos 310 papers do run entregue estavam neste estado: identificador
    conhecido, coluna vazia.
    """
    _, csv_path, _ = preprint_run

    assert _row_for(csv_path, PREPRINT["Title"])["DOI"] == "10.48550/arxiv.2401.00001"


def test_the_resolved_doi_is_the_identity_every_artifact_uses(preprint_run):
    """CSV, `.bib`, `.ris` e a distribuição de pontuações têm de concordar.

    A distribuição é escrita **antes** do filtro de inclusão, a partir do run
    inteiro, e é o que `calibrate_inclusion_threshold` lê para ligar um
    julgamento a uma pontuação. Se a passagem corresse depois dela, o mesmo paper
    teria um id na distribuição e outro no dataset exportado.
    """
    _, csv_path, distribution = preprint_run
    resolved = "10.48550/arxiv.2401.00001"

    bib = sorted(csv_path.parent.rglob("*.bib"))[0].read_text(encoding="utf-8")
    ris = sorted(csv_path.parent.rglob("*.ris"))[0].read_text(encoding="utf-8")
    payload = json.loads(distribution.read_text(encoding="utf-8"))

    assert resolved in _dois_in_csv(csv_path)
    assert resolved in _dois_in_bib(bib)
    assert resolved in _dois_in_ris(ris)

    in_distribution = {
        row["doi"] for row in payload["papers"] if row["title"] == PREPRINT["Title"]
    }
    assert in_distribution == {resolved}, (
        "the score distribution and the exported dataset disagree about which "
        f"paper this is: {in_distribution}"
    )


def test_a_paper_whose_url_names_nothing_keeps_an_empty_column(tmp_path, monkeypatch):
    """Um DOI derivado de uma landing page seria inventado, não lido."""
    papers = [
        {
            "Title": "Blockchain consensus without a landing page DOI",
            "Abstract": "Blockchain consensus.",
            "Year": "2024",
            "URL": "https://core.ac.uk/works/391546543",
            "Source": "CORE",
            "Citations": 0,
            "Type": "article",
            "Venue": "Unknown Venue",
        }
    ]
    _, _ = _run(tmp_path, monkeypatch, papers)
    csv_path = sorted(tmp_path.rglob("*.csv"))[0]

    assert _row_for(csv_path, papers[0]["Title"])["DOI"] == ""


def test_a_preprint_that_has_a_published_version_leaves_as_likely(tmp_path, monkeypatch):
    """O passo corre no pipeline, entre o DOI e a recomputação das pontuações.

    Medido no run entregue: 109 dos 310 papers são preprints e o relatório nomeia
    a venue do próprio preprint — um posting arXiv de 2021 a fazer as vezes da
    comunicação em conferência de que é o preprint. Sem esta ligação o passo
    existe e nunca corre, que é a forma como a correcção desaparece sem falhar.
    """
    papers = _papers() + [dict(PREPRINT)]
    _run(tmp_path, monkeypatch, papers, published=[PUBLISHED_VERSION])
    csv_path = sorted(tmp_path.rglob("*.csv"))[0]
    distribution = sorted(tmp_path.rglob("score_distribution_*.json"))[0]

    row = _row_for(csv_path, PREPRINT["Title"])
    assert row["Peer_Reviewed"] == "Likely", "um registo igual não prova revisão por pares"
    assert row["Venue"] == PUBLISHED_VERSION["Venue"]
    assert row["DOI"] == "10.48550/arxiv.2401.00001", (
        "o DOI do preprint é a chave de identidade do pool e da distribuição; "
        "substituí-lo movê-la-ia depois de o pool ter sido construído"
    )

    published = json.loads(distribution.read_text(encoding="utf-8"))["published_version"]
    assert published["promoted"] == 1
    assert published["promotions"][0]["published_doi"] == PUBLISHED_VERSION["DOI"]
    assert published["promotions"][0]["match"] == "title_and_authors"


def test_a_preprint_that_matches_nothing_keeps_the_venue_it_arrived_with(tmp_path, monkeypatch):
    """Um sítio onde não se encontra nada não é um sítio onde se inventa."""
    papers = _papers() + [dict(PREPRINT)]
    _run(tmp_path, monkeypatch, papers, published=[])
    csv_path = sorted(tmp_path.rglob("*.csv"))[0]
    distribution = sorted(tmp_path.rglob("score_distribution_*.json"))[0]

    assert _row_for(csv_path, PREPRINT["Title"])["Venue"] == "ArXiv"

    published = json.loads(distribution.read_text(encoding="utf-8"))["published_version"]
    assert published["asked"] == 1
    assert published["promoted"] == 0
    assert published["unmatched"] == 1


def test_an_empty_run_writes_its_own_artifacts(tmp_path, monkeypatch):
    """Nothing found is still a run, and it must leave its own files.

    The exporters used to return early on an empty set, so the previous run's
    CSV survived — and a reader found there, as this run's result, exactly the
    papers the threshold had excluded.
    """
    hunter, returned = _run(tmp_path, monkeypatch, [])

    for ext in ("csv", "bib", "ris"):
        written = list(tmp_path.rglob(f"*.{ext}"))
        assert written, f"an empty run wrote no .{ext}"

    from pathlib import Path

    assert returned and Path(returned).exists(), f"run() returned {returned!r}"
    assert hunter.stats["included_final"] == 0
