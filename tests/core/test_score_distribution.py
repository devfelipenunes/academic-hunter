"""The score distribution sidecar, which had no direct test.

Every run writes it and every choice of threshold is argued from it, so its
shape is a contract: the calibration tool keys on ``title`` and ``doi``, and the
run's provenance has to be readable from the file alone — a paper's count is
only evidence when the file also says who answered for it.
"""

import json
import threading
from unittest.mock import MagicMock

from academic_hunter.core.pipeline.steps import RecomputeRanksStep


def make_step(papers, settings=None, timestamp="20260101_000000", threshold=0.0):
    """A rank step whose inclusion threshold is stated rather than leaked by a mock.

    ``inclusion_predicate`` reads ``config.min_inclusion_score()``, and an
    unconfigured ``MagicMock`` answers ``1.0`` — which quietly dropped every
    paper and made the impact counts describe nobody.
    """
    hunter = MagicMock()
    hunter.settings = {"min_relevance_score": 0.0, **(settings or {})}
    hunter.lock = threading.RLock()
    hunter.state.stats = {}
    hunter.semantic_screener = None
    hunter.config.screener_config.return_value = {}
    hunter.config.min_inclusion_score.return_value = threshold
    hunter.scorer.calculate_score.return_value = 0.0
    hunter.consolidated_results = papers
    step = RecomputeRanksStep(hunter)
    step.timestamp = timestamp
    return step


def sidecar(tmp_path, step):
    return json.loads(
        (tmp_path / "run_20260101_000000" / "score_distribution_20260101_000000.json").read_text()
    )


def test_the_sidecar_carries_the_citation_signal(tmp_path):
    papers = {
        "a": {"Title": "A", "DOI": "10.1/a", "Citations": 75, "Citations_Source": "openalex-batch"},
        "b": {"Title": "B", "DOI": "10.1/b", "Citations": 0, "Citations_Source": "none"},
    }
    step = make_step(papers)
    step.hunter.output_dir = str(tmp_path)

    step.run()

    payload = sidecar(tmp_path, step)
    assert "_citation_score" in payload["signals"]
    rows = {row["slug"]: row for row in payload["papers"]}
    assert rows["a"]["_citation_score"] == 1.8808
    assert rows["b"]["_citation_score"] == 0.0
    assert papers["a"]["_citation_score"] == 1.8808


def test_the_sidecar_reports_where_each_count_came_from(tmp_path):
    papers = {
        "a": {"Title": "A", "Citations": 75, "Citations_Source": "openalex-batch"},
        "b": {"Title": "B", "Citations": 0, "Citations_Source": "unresolved"},
        "c": {"Title": "C", "Citations": 0, "Citations_Source": "none"},
        "d": {"Title": "D", "Citations": 12, "Citations_Source": "crossref"},
    }
    step = make_step(papers)
    step.hunter.output_dir = str(tmp_path)

    step.run()

    payload = sidecar(tmp_path, step)
    rows = {row["slug"]: row for row in payload["papers"]}
    assert rows["a"]["citations_source"] == "openalex-batch"
    assert rows["b"]["citations_source"] == "unresolved"

    provenance = payload["citation_provenance"]
    assert provenance["papers"] == 4
    assert provenance["resolved"] == 1
    assert provenance["reported"] == 1
    assert provenance["unresolved"] == 1
    assert provenance["without_identifier"] == 1
    assert provenance["papers"] == len(payload["papers"])


def test_the_sidecar_declares_the_impact_band_the_run_used(tmp_path):
    papers = {
        f"p{i}": {"Title": f"P{i}", "Citations": count}
        for i, count in enumerate([0, 0, 3, 20, 120])
    }
    step = make_step(papers)
    step.hunter.output_dir = str(tmp_path)

    step.run()

    payload = sidecar(tmp_path, step)
    impact = payload["impact"]
    assert impact["papers_measured"] == 3
    assert impact["papers_unmeasured"] == 2
    assert impact["cutoff"] == 20.0
    assert impact["papers_above"] == 2


def test_a_run_with_no_citations_at_all_still_writes_a_readable_sidecar(tmp_path):
    papers = {"a": {"Title": "A", "Citations": 0}, "b": {"Title": "B", "Citations": 0}}
    step = make_step(papers)
    step.hunter.output_dir = str(tmp_path)

    step.run()

    payload = sidecar(tmp_path, step)
    assert payload["impact"]["cutoff"] == 0.0
    assert payload["impact"]["papers_above"] == 0
    assert payload["citation_provenance"]["not_asked"] == 2


def test_the_sidecar_rows_come_out_in_the_same_order_every_time(tmp_path):
    """The file is a run's own record, and a diff of two of them has to mean something.

    The rows were written in the order the papers were inserted, which comes from
    concurrent mining — so two runs of one corpus produced sidecars differing in
    row order alone, the same false signal the CSV was giving.

    The slugs are deliberately the reverse of the DOIs, so an implementation that
    ordered by slug rather than by identity would satisfy "same order both times"
    and still be wrong: two runs would agree with each other and disagree with the
    CSV.
    """
    def tied(slug, doi):
        return {slug: {"Title": slug, "DOI": doi, "_kw_score": 9.0, "Relevance_Score": 4.0}}

    forward = make_step(tied("z", "10.1/a") | tied("a", "10.1/b"))
    backward = make_step(tied("a", "10.1/b") | tied("z", "10.1/a"), timestamp="20260101_000001")
    for step in (forward, backward):
        step.hunter.output_dir = str(tmp_path)

    forward.run()
    backward.run()

    assert [row["slug"] for row in sidecar(tmp_path, forward)["papers"]] == ["z", "a"]
    assert [
        row["slug"]
        for row in json.loads(
            (tmp_path / "run_20260101_000001" / "score_distribution_20260101_000001.json").read_text()
        )["papers"]
    ] == ["z", "a"]


def test_the_impact_band_describes_the_papers_the_report_lists(tmp_path):
    """Counting the evaluated set instead left the two lines of the same report disagreeing.

    A paper the predicate excluded was still measured into ``papers_measured``,
    so the impact section quoted one more paper than the coverage line above it
    and the table below it could show.
    """
    papers = {
        "kept": {"Title": "Kept", "Citations": 120, "_kw_score": 9.0},
        "cited_but_excluded": {"Title": "Excluded", "Citations": 75, "_kw_score": 1.0},
        "kept_zero": {"Title": "Kept zero", "Citations": 0, "_kw_score": 8.0},
    }
    step = make_step(papers, threshold=5.0)
    step.hunter.output_dir = str(tmp_path)

    step.run()

    payload = sidecar(tmp_path, step)
    assert step.hunter.state.stats["excluded_technical_score"] == 1
    assert payload["impact"]["papers_measured"] == 1
    assert payload["impact"]["papers_unmeasured"] == 1
    assert payload["impact"]["papers_measured"] + payload["impact"]["papers_unmeasured"] == 2
    assert payload["citation_provenance"]["papers"] == 3


def signals_papers():
    """Three papers whose embedding and citation signals both vary."""
    return {
        "a": {"Title": "alpha self-sovereign", "Abstract": "identity wallet", "_kw_score": 9.0,
              "_sem_score": 0.9, "Citations": 120},
        "b": {"Title": "beta ledger", "Abstract": "distributed ledger", "_kw_score": 4.0,
              "_sem_score": 0.4, "Citations": 12},
        "c": {"Title": "gamma unrelated", "Abstract": "unrelated", "_kw_score": 1.0,
              "_sem_score": 0.1, "Citations": 0},
    }


def test_query_mode_records_the_embedding_it_multiplied_by_zero(tmp_path):
    """The run computed the embedding and then used none of it, and it says so.

    ``ranking_query`` with no ``fusion_weights`` forces 1.0/0.0. Every paper is
    scored on its embedding all the same, and the recorded weights are the ones
    that were applied, not the ones in the config file.
    """
    step = make_step(signals_papers(), {"ranking_query": "self-sovereign identity"})
    step.hunter.output_dir = str(tmp_path)

    step.run()

    fusion = sidecar(tmp_path, step)["fusion"]
    assert fusion["weights"]["embedding"] == 0.0
    assert fusion["weights"]["keyword"] == 1.0
    assert "embedding" in fusion["discarded"]
    assert fusion["strategy"] == "weighted_norm"


def test_configured_weights_are_recorded_as_they_were_configured(tmp_path):
    weights = {"keyword": 0.5, "embedding": 0.5, "citation": 1.0}
    step = make_step(signals_papers(), {"fusion_weights": weights})
    step.hunter.output_dir = str(tmp_path)

    step.run()

    fusion = sidecar(tmp_path, step)["fusion"]
    assert fusion["weights"] == weights
    assert fusion["discarded"] == []


def test_a_citation_weight_on_counts_that_do_not_vary_is_recorded_as_zero(tmp_path):
    """Nothing to order, so the weight buys nothing — and the record says zero.

    A constant citation list is flattened to zeros by ``_minmax``; a weight that
    takes its share of the total without contributing a value would rescale every
    score. It is not listed as discarded, because there is no signal being
    thrown away: there is no signal.
    """
    papers = signals_papers()
    for paper in papers.values():
        paper["Citations"] = 7
    step = make_step(papers, {"fusion_weights": {"keyword": 0.5, "embedding": 0.5, "citation": 1.0}})
    step.hunter.output_dir = str(tmp_path)

    step.run()

    fusion = sidecar(tmp_path, step)["fusion"]
    assert fusion["weights"]["citation"] == 0.0
    assert fusion["discarded"] == []


def test_a_run_without_a_screener_does_not_claim_the_embedding_was_a_signal(tmp_path):
    """A flat embedding is not a discarded signal — there was none to discard."""
    papers = signals_papers()
    for paper in papers.values():
        paper["_sem_score"] = 0.0
    step = make_step(papers, {"ranking_query": "self-sovereign identity"})
    step.hunter.output_dir = str(tmp_path)

    step.run()

    assert "embedding" not in sidecar(tmp_path, step)["fusion"]["discarded"]


def test_recording_the_weights_does_not_move_a_single_score(tmp_path):
    """The lot is visibility, and this is the test that says so.

    Literal per-paper scores, pinned against what the run produced before the
    ``fusion`` block existed: a change that makes the zero readable must not be a
    change that alters the ranking it is describing.
    """
    papers = signals_papers()
    step = make_step(papers, {"ranking_query": "self-sovereign identity"})
    step.hunter.output_dir = str(tmp_path)

    step.run()

    assert [papers[slug]["Relevance_Score"] for slug in ("a", "b", "c")] == [10.0, 0.0, 0.0]
