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

#: O DOI canônico de cada um, depois de `normalize_doi`: sem prefixo, minúsculo.
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


def _run(tmp_path, monkeypatch, papers):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(CONFIG), encoding="utf-8")
    hunter = AcademicHunter(config_path=str(config_path), output_dir=str(tmp_path))

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
