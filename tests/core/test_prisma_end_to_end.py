"""O fluxo PRISMA de um run de verdade tem de fechar.

Os testes de `flow_counts` conferem a aritmética sobre números escritos à mão.
Este roda o pipeline inteiro — coleta, dedup, filtros, ranking, limiar e
exportação — e lê o diagrama que saiu, que é o artefato que um revisor confere.
"""

import json
import re

import pytest

from academic_hunter import AcademicHunter

CONFIG = {
    "settings": {"min_relevance_score": 5.0, "start_year": 2024},
    "anchors": {"test": ["blockchain"]},
    "technical_strings": {"test": ["latency", "consensus"]},
    "technical_weights": {"blockchain": 5.0, "latency": 3.0, "consensus": 2.0},
}

#: `Passed` aparece três vezes no diagrama — uma por etapa de triagem — então a
#: ordem é o que identifica cada uma.
PASSED_STAGES = ("temporal filter", "anchor screening", "technical evaluation")


def paper(title, abstract, citations=0):
    return {
        "Title": title,
        "Abstract": abstract,
        "Year": "2024",
        "URL": f"http://example.com/{title.replace(' ', '-').lower()}",
        "Source": "Mock",
        "Citations": citations,
        "Type": "article",
        "Venue": "Mock Venue",
    }


#: Metade passa no filtro de âncora; entre esses, a densidade técnica varia o
#: bastante para o limiar de score cortar alguns.
PAPERS = [
    paper("Blockchain latency in payment rails", "Blockchain latency consensus throughput.", 12),
    paper("Blockchain consensus protocols", "Blockchain consensus and latency trade-offs.", 9),
    paper("A blockchain survey", "Blockchain systems, broadly.", 5),
    paper("Ledgers without anchors", "Nothing about the configured terms.", 1),
    paper("Distributed systems", "Unrelated material entirely.", 0),
]


def _edges(markdown):
    """As arestas do diagrama, na ordem em que aparecem."""
    return [(label.strip(), int(value)) for label, value in
            re.findall(r"-->\|([^:]+):\s*(\d+)\|", markdown)]


@pytest.fixture
def run_output(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(CONFIG), encoding="utf-8")
    hunter = AcademicHunter(config_path=str(config_path), output_dir=str(tmp_path))

    for name in (
        "fetch_arxiv", "fetch_crossref", "fetch_semantic_scholar", "fetch_openalex",
        "fetch_core_ac", "fetch_dblp", "fetch_doaj",
    ):
        monkeypatch.setattr(
            AcademicHunter, name, lambda *a, **k: [p.copy() for p in PAPERS]
        )

    returned = hunter.run(limit_per_source=1)

    reports = list(tmp_path.rglob("FLUXO_PRISMA_*.md"))
    assert reports, "no PRISMA report was written"
    return hunter, _edges(reports[0].read_text(encoding="utf-8")), returned


def test_run_returns_a_path_that_exists(run_output):
    """`run_search` hands this path back to the agent as the report.

    The manager returned `output_dir/RELATORIO_ELITE_<ts>.md` while the exporters
    wrote into `output_dir/run_<ts>/`, so every consumer that followed it got a
    file that was never there.
    """
    from pathlib import Path

    _, _, returned = run_output

    assert returned, "run() returned nothing to point at"
    assert Path(returned).exists(), f"run() returned a path that does not exist: {returned}"


def test_the_exported_flow_closes_at_technical_evaluation(run_output):
    hunter, edges, _ = run_output
    labels = dict(edges)

    passed = [value for label, value in edges if label == "Passed"]
    assert len(passed) == len(PASSED_STAGES)
    _, evaluated, final = passed

    assert labels["Failed Score"] == hunter.stats["excluded_technical_score"]
    assert final == hunter.stats["included_final"]
    assert evaluated == labels["Failed Score"] + final, (
        f"{evaluated} entered technical evaluation but "
        f"{labels['Failed Score']} + {final} left it"
    )


def test_the_stages_above_it_chain_without_gaps(run_output):
    _, edges, _ = run_output
    labels = dict(edges)

    passed = [value for label, value in edges if label == "Passed"]
    after_year, evaluated, _ = passed

    # The temporal edge is labelled with the cutoff year, so it is matched by
    # prefix rather than by name.
    out_of_range = next(value for label, value in edges if label.startswith("Published <"))

    assert after_year == evaluated + labels["No Core Anchors"]
    assert labels["Unique Records"] == after_year + out_of_range
