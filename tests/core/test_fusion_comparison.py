"""The fusion comparator measures the shipped rule, and says what it cannot.

The table it replaces was measured by a script that left the repository, so the
first thing the new one has to prove is that it is not a second formula: the
shipped rule, over a run's own stored signals, has to reproduce the ordering the
run itself produced. The second thing is that its refusals are visible — a rule
reading a column the run never wrote, or one that does not vary, produces a
column of numbers that reads as a measurement, and a table showing it would be
worse than no table.
"""

import json
import tempfile
from pathlib import Path

import pytest

from academic_hunter.core.evaluation import doc_id_for, load_qrels
from academic_hunter.core.evaluation.comparison import (
    DEFAULT_STRATEGIES,
    NOT_REPRODUCIBLE,
    Strategy,
    compare,
    load_distribution,
    render,
)
from academic_hunter.core.nlp.fusion import IMPLEMENTED_STRATEGIES, fuse_scores

POOL = [f"doi:10.1/{letter}" for letter in "abcde"]


def paper(title, doi, kw, sem, cit, citations=None, own=None):
    """One row of a score distribution, with only the columns given."""
    return {
        "title": title,
        "doi": doi,
        "_kw_score": kw,
        "_sem_score": sem,
        "_citation_score": cit,
        "citations": cit if citations is None else citations,
        "Relevance_Score": kw if own is None else own,
    }


def distribution(papers, run="20261001_000000", **extra):
    return {"run": run, "papers": papers, "counts": {"evaluated": len(papers)}, **extra}


def query(text="a topic", grades=None, pool=None, topic=""):
    entry = {"text": text, "judgments": grades or {}}
    if pool is not None:
        entry["pool"] = pool
    if topic:
        entry["topic"] = topic
    return entry


def qrels_of(queries, description="fixture"):
    return {"description": description, "queries": queries}


@pytest.fixture
def five():
    """Five documents whose id is derivable and whose three signals all vary."""
    return [
        paper("Alpha", "10.1/a", 30.0, 0.1, 9.0),
        paper("Beta", "10.1/b", 20.0, 0.9, 2.0),
        paper("Gamma", "10.1/c", 10.0, 0.5, 5.0),
        paper("Delta", "10.1/d", 5.0, 0.2, 1.0),
        paper("Epsilon", "10.1/e", 1.0, 0.7, 0.0),
    ]


@pytest.fixture
def judged(tmp_path):
    def _make(payload):
        path = tmp_path / "qrels.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return load_qrels(path)

    return _make


@pytest.fixture
def graded(judged):
    """The five documents judged, each with its own grade."""
    grades = dict(zip(POOL, [2, 1, 0, 1, 0]))
    return judged(qrels_of({"q1": query(grades=grades, pool=POOL)}))


def _row(result, label):
    for row in result.rows:
        if row.label == label:
            return row
    raise AssertionError(f"{label} is not among the rows: {[r.label for r in result.rows]}")


def _skipped(result, label):
    for name, reason in result.skipped:
        if name == label:
            return reason
    raise AssertionError(f"{label} was not left out: {result.skipped}")


def test_the_default_rows_only_name_rules_the_fusion_implements():
    """A label is not a measurement: every other string is `weighted_norm`."""
    for strategy in DEFAULT_STRATEGIES:
        if strategy.strategy:
            assert strategy.strategy in IMPLEMENTED_STRATEGIES, strategy


def test_the_four_rules_that_cannot_be_reproduced_are_named_as_such():
    """They were the deleted script's, and `fuse_scores` implements two rules."""
    names = {name for name, _ in NOT_REPRODUCIBLE}

    assert names == {"max_rank", "rrf_60", "arith_rank", "min_rank"}
    assert not names & set(IMPLEMENTED_STRATEGIES)


def test_a_rule_the_shipping_fusion_does_not_implement_is_refused(five, judged):
    """Without the guard the row carries `weighted_norm`'s numbers under
    `rrf_60`'s name — the exact failure the exported list exists to prevent."""
    qrels = judged(qrels_of({"q1": query(grades={"doi:10.1/a": 2}, pool=POOL)}))

    with pytest.raises(ValueError, match="rrf_60"):
        compare(
            distribution(five),
            qrels,
            strategies=(Strategy("rrf_60", strategy="rrf_60", requires=("sparse",)),),
        )


def test_a_distribution_with_no_papers_is_refused(judged):
    qrels = judged(qrels_of({"q1": query(grades={"doi:10.1/a": 2})}))

    with pytest.raises(ValueError, match="no papers"):
        compare(distribution([]), qrels)


def test_the_shipped_rule_reproduces_the_ranking_the_run_shipped(five, graded):
    """The comparator must measure the code that runs, not a restatement of it.

    Each fixture row's own score is its keyword score, which is the ordering
    `weighted_norm` produces at a keyword weight of one: a second fusion formula
    inside the comparator would drift from that here first.
    """
    result = compare(distribution(five), graded)

    assert _row(result, "weighted_norm_1_0").rankings == _row(
        result, "run's own (Relevance_Score)"
    ).rankings


def test_the_comparison_is_the_same_however_the_rows_are_ordered(judged):
    """Ties and iteration order must not move a table that decides a weight."""
    tied = [
        paper("Alpha", "10.1/a", 30.0, 0.1, 9.0),
        paper("Beta", "10.1/b", 30.0, 0.1, 2.0),
        paper("Gamma", "10.1/c", 20.0, 0.5, 5.0),
        paper("Delta", "10.1/d", 5.0, 0.2, 1.0),
        paper("Epsilon", "10.1/e", 1.0, 0.7, 0.0),
    ]
    qrels = judged(qrels_of({"q1": query(grades=dict(zip(POOL, [2, 1, 0, 1, 0])), pool=POOL)}))

    first = compare(distribution(tied), qrels)
    second = compare(distribution(list(reversed(tied))), qrels)

    assert first.rows
    assert [row.rankings for row in first.rows] == [row.rankings for row in second.rows]


def test_a_rule_whose_column_the_run_never_recorded_is_left_out_and_named(five, graded):
    """An absent `_sem_score` is not a `_sem_score` of zero, and a row of zeros
    in its place says the embedding scored nothing."""
    rows = [{k: v for k, v in p.items() if k != "_sem_score"} for p in five]

    result = compare(distribution(rows), graded)

    assert "`_sem_score`" in _skipped(result, "weighted_norm_0_1")
    assert "`_sem_score`" in _skipped(result, "rank_geometric")
    assert "`_sem_score`" in _skipped(result, "weighted_norm_70_30")
    assert all(row.label != "rank_geometric" for row in result.rows)


def test_a_rule_whose_column_never_varies_is_left_out_and_named(five, graded):
    """`percentile_ranks` of a constant is the document's position in the input,
    so `rank_geometric` over a flat column would rank by iteration order."""
    rows = [dict(p, _sem_score=0.5) for p in five]

    result = compare(distribution(rows), graded)

    reason = _skipped(result, "rank_geometric")
    assert "`_sem_score`" in reason
    assert "constant" in reason
    assert all(row.label != "rank_geometric" for row in result.rows)
    assert _row(result, "weighted_norm_1_0").rankings


def test_a_citation_weight_the_fusion_reads_as_zero_does_not_become_a_row(five, graded):
    """The row would carry the other signals' ratio under a three-signal label."""
    rows = [dict(p, _citation_score=1.0) for p in five]

    result = compare(distribution(rows), graded)

    reason = _skipped(result, "weighted_norm_cit_10")
    assert "resolve_weights" in reason
    assert "`_citation_score`" in reason
    assert all(row.label != "weighted_norm_cit_10" for row in result.rows)
    assert _row(result, "weighted_norm_70_30").rankings


def test_the_citation_column_is_derived_when_the_run_did_not_record_one(five, graded):
    """The derivation is exact — `citation_signal` is what the step computes —
    and the report says it happened instead of passing it off as the run's own."""
    rows = [{k: v for k, v in p.items() if k != "_citation_score"} for p in five]

    result = compare(distribution(rows), graded)

    assert result.citation_derived is True
    assert result.citation_column == "citations"
    assert "derived" in render(result)
    assert _row(result, "citations_baseline").rankings


def test_the_citation_column_is_the_run_s_own_when_it_recorded_one(five, graded):
    result = compare(distribution(five), graded)

    assert result.citation_derived is False
    assert result.citation_column == "_citation_score"
    assert "as the run recorded it" in render(result)


def test_the_sparse_side_is_bm25_when_the_run_was_ordered_by_a_query(five, graded):
    """The pipeline takes that fork, so a comparison that did not would measure
    a rule no run applies."""
    rows = [dict(p, _bm25_score=p["_kw_score"] * 2) for p in five]

    result = compare(distribution(rows), graded)

    assert result.sparse_signal == "_bm25_score"
    assert "BM25" in render(result)


def test_the_sparse_side_is_the_domain_score_without_a_ranking_query(five, graded):
    result = compare(distribution(five), graded)

    assert result.sparse_signal == "_kw_score"
    assert "not ordered by a query" in render(result)


def test_only_the_declared_pool_is_ranked(five, judged):
    """A judged document outside the pool was never a candidate for this query,
    and ranking it would measure the pool rather than the rule."""
    declared = POOL[:3]
    qrels = judged(qrels_of({"q1": query(grades=dict.fromkeys(POOL, 1), pool=declared)}))

    result = compare(distribution(five), qrels)

    ranking = _row(result, "weighted_norm_1_0").rankings["q1"]
    assert sorted(ranking) == sorted(declared)


def test_a_pool_document_the_run_never_scored_is_counted_not_scored(five, judged):
    """No rule compared here can retrieve it, so it is named rather than left to
    depress every recall figure in silence."""
    pool = POOL + ["doi:10.1/z"]
    qrels = judged(qrels_of({"q1": query(grades=dict.fromkeys(pool, 1), pool=pool)}))

    result = compare(distribution(five), qrels)

    assert result.unscored == ["doi:10.1/z"]
    assert "doi:10.1/z" not in _row(result, "weighted_norm_1_0").rankings["q1"]
    assert "no row in the distribution" in render(result)


def test_two_rows_with_one_id_collapse_onto_the_copy_the_run_scored_higher(judged):
    """Ranking the study by its worse record would lose what the better one
    qualifies for."""
    rows = [
        paper("Alpha preprint", "10.1/a", 0.5, 0.1, 9.0, own=99.0),
        paper("Alpha", "10.1/a", 30.0, 0.1, 9.0),
        paper("Beta", "10.1/b", 20.0, 0.9, 2.0),
        paper("Gamma", "10.1/c", 10.0, 0.5, 5.0),
    ]
    pool = [f"doi:10.1/{letter}" for letter in "abc"]
    qrels = judged(qrels_of({"q1": query(grades=dict.fromkeys(pool, 1), pool=pool)}))

    result = compare(distribution(rows), qrels)

    assert result.duplicate_rows == 1
    assert result.papers == 4
    assert "collapsed onto one document id" in render(result)
    assert _row(result, "run's own (Relevance_Score)").rankings["q1"][0] == "doi:10.1/a"
    assert _row(result, "weighted_norm_1_0").rankings["q1"][-1] == "doi:10.1/a"


def test_without_a_judged_document_the_table_is_not_printed(five, judged):
    """Empty is the honest answer: nothing in the collection says which of these
    papers is relevant, so every rule would score zero for the same reason."""
    qrels = judged(qrels_of({"q1": query(grades={"doi:10.9/absent": 2}, pool=POOL)}))

    result = compare(distribution(five), qrels)
    report = render(result)

    assert result.judged_and_scored == 0
    assert "No judgments to measure against" in report
    assert "| Rule |" not in report


def test_the_report_names_every_row_and_every_rule_it_left_out(five, graded):
    rows = [{k: v for k, v in p.items() if k != "_sem_score"} for p in five]

    report = render(compare(distribution(rows), graded))

    assert "## What each row is" in report
    for row in ("run's own (Relevance_Score)", "weighted_norm_1_0", "citations_baseline"):
        assert f"- `{row}` — " in report
    assert "## Not measured, and why" in report
    assert "## Not reproducible from this repository" in report
    for name, _ in NOT_REPRODUCIBLE:
        assert f"- `{name}` — " in report


def test_per_topic_tables_appear_only_when_there_is_more_than_one_topic(five, judged):
    """A mean over unrelated corpora hides a rule that helps one and ruins the
    other."""
    one = judged(qrels_of({"q1": query(grades=dict(zip(POOL, [2, 1, 0, 1, 0])), pool=POOL)}))
    assert compare(distribution(five), one).per_topic == {}
    assert "## Per topic" not in render(compare(distribution(five), one))

    two = judged(
        qrels_of(
            {
                "q1": query(
                    text="one", grades=dict(zip(POOL, [2, 1, 0, 1, 0])), pool=POOL, topic="ledgers"
                ),
                "q2": query(
                    text="two", grades=dict(zip(POOL, [0, 1, 2, 0, 1])), pool=POOL, topic="wallets"
                ),
            }
        )
    )
    report = render(compare(distribution(five), two))

    assert "## Per topic" in report
    assert "### `ledgers`" in report
    assert "### `wallets`" in report


def test_every_metric_column_is_reported_for_every_measured_row(five, graded):
    """A row with a `None` cell would render as an em dash and read as a zero."""
    result = compare(distribution(five), graded)

    assert result.rows
    for row in result.rows:
        assert set(result.metric_columns) <= set(row.metrics), (row.label, row.metrics)


def _recorded_runs():
    results = Path(__file__).resolve().parent.parent.parent / "results"
    return sorted(results.glob("run_*/score_distribution_*.json"))


def _self_qrels(distribution):
    """A judged collection made from the run itself, to exercise the real path.

    The ids, the pools and the grades are the run's own top documents in the
    run's own order. Nothing here is evidence about retrieval quality — the
    synthetic tests above are where quality is argued — and it exists so the
    comparator is driven over a distribution with the columns, the duplicate
    rows and the id derivations a real one has, which a fixture cannot supply.
    """
    papers = [row for row in distribution["papers"] if isinstance(row, dict)]
    ordered = sorted(
        papers,
        key=lambda row: (
            -float(row.get("Relevance_Score") or 0.0),
            doc_id_for(str(row.get("title") or ""), str(row.get("doi") or "")),
        ),
    )
    pool = [
        doc_id_for(str(row.get("title") or ""), str(row.get("doi") or "")) for row in ordered[:50]
    ]
    grades = {doc_id: 2 if rank < 10 else 1 for rank, doc_id in enumerate(pool)}
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    with handle:
        json.dump(qrels_of({"q1": query(grades=grades, pool=pool)}), handle)
    return load_qrels(handle.name)


recorded = pytest.mark.skipif(
    not _recorded_runs(),
    reason="no run under results/ to measure; they are written by run_search and gitignored",
)


@recorded
def test_every_recorded_run_accounts_for_every_rule_it_could_not_measure():
    """A rule that is neither a row nor a named skip has vanished, and the
    table would look complete while missing it."""
    for path in _recorded_runs():
        result = compare(
            load_distribution(path), _self_qrels(load_distribution(path)), judged_collection="self"
        )
        accounted = {row.label for row in result.rows} | {label for label, _ in result.skipped}
        assert accounted == {s.label for s in DEFAULT_STRATEGIES}, path
        assert _row(result, "run's own (Relevance_Score)").rankings, path
        for row in result.rows:
            for ranking in row.rankings.values():
                assert len(set(ranking)) == len(ranking), (path, row.label)


@recorded
def test_the_recorded_score_is_a_rule_of_the_shipping_fusion():
    """The premise of the whole table: `Relevance_Score` came from `fuse_scores`
    over the columns the run itself wrote.

    Checked at the precision the score was stored at, derived from the stored
    values rather than fixed here — these runs write one decimal, and a
    comparison that demanded full precision would report every run as
    irreproducible while the run was correct. What it does catch is a change to
    `weighted_norm` or to which column carries the sparse signal: the rule that
    reproduced a run today would stop reproducing it.
    """
    for path in _recorded_runs():
        distribution = load_distribution(path)
        papers = [row for row in distribution["papers"] if isinstance(row, dict)]
        stored = [float(row.get("Relevance_Score") or 0.0) for row in papers]
        decimals = max(
            len(repr(value).split(".")[1]) if "." in repr(value) else 0 for value in stored
        )
        columns = {key for row in papers for key in row}
        sparse = "_bm25_score" if "_bm25_score" in columns else "_kw_score"
        sparse_values = [float(row.get(sparse) or 0.0) for row in papers]
        sem_values = [float(row.get("_sem_score") or 0.0) for row in papers]

        reproduced = []
        for strategy in DEFAULT_STRATEGIES:
            if strategy.signal:
                continue
            fused = fuse_scores(
                sparse_values,
                sem_values,
                strategy=strategy.strategy,
                weights=strategy.weights,
            )
            if all(abs(round(value, decimals) - own) < 1e-9 for value, own in zip(fused, stored)):
                reproduced.append(strategy.label)

        assert reproduced, (
            f"{path}: no rule of fuse_scores reproduces the stored Relevance_Score "
            f"at {decimals} decimals over `{sparse}`; the table's premise does not hold "
            "for this run"
        )
