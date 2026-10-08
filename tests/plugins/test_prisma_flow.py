"""O fluxo PRISMA tem de fechar: o que entra na avaliação técnica é o que sai dela.

Fechar no cabeçalho não chega. A tabela por fonte tem de somar ao mesmo total,
senão o relatório contradiz os seus próprios números — foi o que aconteceu no run
de "blockchain e IA", com a coluna a zero e o cabeçalho a 214.
"""

import logging
import threading
from unittest.mock import MagicMock

from academic_hunter.core.infra.state import SearchState
from academic_hunter.core.pipeline.steps import RecomputeRanksStep
from academic_hunter.plugins.exporters.prisma import flow_counts


def _step_with_papers(papers, min_score):
    """Um RecomputeRanksStep real sobre papers reais, com o scorer reduzido a um stub.

    ``state`` is the real ``SearchState``: ``track_exclusion`` is what writes the
    per-source table, and a mock would answer every call without recording any of
    it -- which is precisely the failure being tested.

    ``min_score`` is the inclusion threshold, and it gates ``_kw_score`` -- an
    absolute property of the paper -- rather than the run-relative
    ``Relevance_Score`` the tests above this one were written against.
    """
    hunter = MagicMock()
    hunter.settings = {"fusion_weights": {"keyword": 1.0, "embedding": 0.0}}
    hunter.config.min_inclusion_score.return_value = min_score
    hunter.lock = threading.RLock()
    hunter.state = SearchState()
    hunter.semantic_screener = None
    hunter.config.screener_config.return_value = {}
    hunter.consolidated_results = papers
    return RecomputeRanksStep(hunter)


def _score_column(stats):
    return sum(
        entry.get("score", 0) for entry in stats.get("exclusions_by_source", {}).values()
    )

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


def _run_that_drops_two(papers=None):
    """Cinco papers, dois abaixo do limiar, e o que o rank step escreve no estado.

    The `_kw_score` values are the whole input: the threshold is compared
    against them directly, so 5.0 drops exactly d and e.
    """
    if papers is None:
        papers = {
            "a": {"Source": "ArXiv", "_kw_score": 10.0},
            "b": {"Source": "CORE, ArXiv", "_kw_score": 8.0},
            "c": {"Source": "CORE", "_kw_score": 6.0},
            "d": {"Source": "ArXiv", "_kw_score": 4.0},
            "e": {"Source": "CORE, DOAJ", "_kw_score": 2.0},
        }
    step = _step_with_papers(papers, min_score=5.0)
    step.run()
    return step.hunter.state.stats


def test_the_score_column_sums_to_the_headline():
    """The bug the run exposed: a column of zeros under a headline of 214.

    The exporter prints both, an arm's length apart, and they disagreed. A
    reviewer reading the table would count no score exclusions at all.
    """
    stats = _run_that_drops_two()

    assert stats["excluded_technical_score"] == 2
    assert stats["included_final"] == 3
    assert _score_column(stats) == 2


def test_each_drop_is_charged_to_the_source_that_carried_the_paper():
    stats = _run_that_drops_two()

    assert stats["exclusions_by_source"]["ArXiv"]["score"] == 1
    assert stats["exclusions_by_source"]["CORE"]["score"] == 1


def test_a_paper_from_two_databases_lands_in_one_row():
    """Otherwise it would be counted twice and the column would overshoot.

    `Source` is a comma-joined list, and the run's papers carry several. The
    rule is the first, which is the one the screening's own adjustment uses.
    """
    stats = _run_that_drops_two()

    assert "CORE, DOAJ" not in stats["exclusions_by_source"]
    assert "CORE, ArXiv" not in stats["exclusions_by_source"]
    assert _score_column(stats) == stats["excluded_technical_score"]


def test_the_screening_counters_are_replaced_and_not_added_to():
    """Both stages count the same papers, so both counters cannot stand.

    Registration writes the paper into `consolidated_results` before it tests
    it, so everything the screening excluded on score is evaluated again here.
    Adding the two would double the column.
    """
    papers = {
        "a": {"Source": "ArXiv", "_kw_score": 10.0},
        "b": {"Source": "ArXiv", "_kw_score": 2.0},
    }
    step = _step_with_papers(papers, min_score=5.0)
    step.hunter.state.stats["exclusions_by_source"] = {
        "ArXiv": {"year": 0, "anchor": 0, "score": 7},
        "CORE": {"year": 3, "anchor": 4, "score": 5},
    }

    step.run()

    assert step.hunter.state.stats["exclusions_by_source"]["ArXiv"]["score"] == 1
    assert step.hunter.state.stats["exclusions_by_source"]["CORE"]["score"] == 0
    assert _score_column(step.hunter.state.stats) == 1


def test_clearing_the_column_leaves_the_other_columns_alone():
    """Year and anchor are counted only during screening and are not recounted."""
    papers = {
        "a": {"Source": "ArXiv", "_kw_score": 10.0},
        "b": {"Source": "ArXiv", "_kw_score": 2.0},
    }
    step = _step_with_papers(papers, min_score=5.0)
    step.hunter.state.stats["exclusions_by_source"] = {
        "ArXiv": {"year": 3, "anchor": 9, "score": 4},
    }

    step.run()

    assert step.hunter.state.stats["exclusions_by_source"]["ArXiv"] == {
        "year": 3, "anchor": 9, "score": 1,
    }


def test_a_source_with_no_row_yet_gets_one():
    """A source whose papers all passed the earlier gates has no entry to bump."""
    papers = {
        "a": {"Source": "ArXiv", "_kw_score": 10.0},
        "b": {"Source": "DOAJ", "_kw_score": 2.0},
    }
    step = _step_with_papers(papers, min_score=5.0)

    step.run()

    assert step.hunter.state.stats["exclusions_by_source"]["DOAJ"]["score"] == 1
    assert _score_column(step.hunter.state.stats) == 1


def test_a_paper_that_names_no_source_is_reported_rather_than_dropped(caplog):
    """It cannot go in a row it has no name for, so it is named in the log.

    Silence here would put the column one short of the headline with nothing
    anywhere saying why -- the defect this whole change is about.
    """
    papers = {
        "a": {"Source": "ArXiv", "_kw_score": 10.0},
        "b": {"Source": "", "_kw_score": 2.0},
    }
    step = _step_with_papers(papers, min_score=5.0)

    with caplog.at_level(logging.WARNING):
        step.run()

    assert "names no source" in caplog.text
    assert step.hunter.state.stats["excluded_technical_score"] == 1
    assert _score_column(step.hunter.state.stats) == 0


def test_the_headline_and_the_column_close_the_flow_together():
    """End to end: the table and the diagram are read as one document."""
    stats = _run_that_drops_two()
    stats.update(
        {
            "identified": {"ArXiv": 40, "CORE": 30, "DOAJ": 10},
            "duplicates_removed": 9,
            "excluded_year": 4,
            "excluded_anchors": 62,
        }
    )

    counts = flow_counts(stats)

    assert counts["evaluated"] == 5
    assert counts["excluded_tech"] + counts["final"] == 5
    assert counts["closes"] is True
    assert _score_column(stats) == counts["excluded_tech"]
