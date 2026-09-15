"""O fluxo PRISMA tem de fechar: o que entra na avaliação técnica é o que sai dela."""

from academic_hunter.plugins.exporters.prisma import flow_counts

#: O run de 10/09/2026 como ele foi gravado: 58 papers entraram na avaliação
#: técnica, 40 foram incluídos, e a contagem dos 18 excluídos foi parar numa
#: segunda chave que o diagrama não lia.
RUN_20260910 = {
    "identified": {"OpenAlex": 100, "Crossref": 28},
    "duplicates_removed": 26,
    "excluded_year": 8,
    "excluded_anchors": 36,
    "excluded_technical_score": 0,
    "included_final": 40,
}


def test_the_stages_chain_from_the_identification_total():
    counts = flow_counts(
        {
            "identified": {"A": 100, "B": 28},
            "duplicates_removed": 26,
            "excluded_year": 8,
            "excluded_anchors": 36,
            "excluded_technical_score": 18,
            "included_final": 40,
        }
    )
    assert counts["total_identified"] == 128
    assert counts["unique"] == 102
    assert counts["after_year"] == 94
    assert counts["evaluated"] == 58
    assert counts["closes"] is True


def test_the_run_that_reported_a_hole_in_the_flow_is_flagged():
    counts = flow_counts(RUN_20260910)
    assert counts["evaluated"] == 58
    assert counts["excluded_tech"] + counts["final"] == 40
    assert counts["closes"] is False


def test_a_flow_whose_exclusions_are_all_recorded_closes():
    assert flow_counts(dict(RUN_20260910, excluded_technical_score=18))["closes"] is True


def test_an_empty_run_closes_at_zero():
    assert flow_counts({})["closes"] is True
