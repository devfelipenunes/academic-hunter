"""Compare the fusion rules on a run's own signals, against a judged collection.

The tool could already choose the inclusion threshold from measurements and
still had to guess the weights: :mod:`.calibration` sweeps one number against one
run, while the weights decide the ordering that number is applied to.
``evaluation/README.md`` used to carry a table of strategy against nDCG, measured
by a script that left the repository with ``papers/`` in ``6a48f1c`` — and a
table nobody can rerun is an assertion, not a measurement.

This rebuilds it against :mod:`academic_hunter.core.nlp.fusion`, *the code that
ships*. It calls ``fuse_scores`` and ``resolve_weights`` rather than restating
the formula, because a second implementation is free to drift from the first,
and the measurement would then describe a rule no run applies.
``evaluation/fusion_comparison.py`` is the command-line front end; this module
is the part the MCP tool can import, since a root-level script directory is not
on the installed package's path.

What it measures, and what it refuses to

- The **corpus is the run's own papers** and, for each query, that query's
  declared pool. Every rule is ranked on the same candidate set, so a difference
  in the metrics is attributable to the rule and not to a different retrieval.
- The **signals are the run's own columns**, read from the score distribution.
  The sparse signal is ``_bm25_score`` when the run had a ``ranking_query`` and
  ``_kw_score`` when it did not, because that is the fork the pipeline itself
  takes; the report names which one was used.
- The **citation signal** is ``_citation_score`` when the run recorded it and
  ``citation_signal(citations)`` when it did not. The two are the same number by
  construction — that function is what the step computes — so the fallback is
  exact rather than approximate, and the report says which happened instead of
  presenting a derivation as the run's own record.
- A rule is **left out and named** when either of the two columns it would read
  cannot carry a measurement: one the run never recorded, or one that does not
  vary. Both produce a column of numbers that reads as a result, and neither is
  a result. A missing column in a row of zeros says "this signal scored
  nothing" when it means "this signal was never computed"; a constant one gives
  every rule a different way to invent an ordering — ``weighted_norm`` flattens
  it away and measures the remaining signals under a label naming all of them
  (which is exactly what ``resolve_weights`` does to a citation weight on a
  corpus whose counts are all equal), and ``rank_geometric`` is worse, because
  ``percentile_ranks`` of a constant is the document's *position in the input*,
  so the row would rank by the caller's iteration order and look measured. An
  input column that is constant therefore makes the row unmeasurable, whatever
  the rule would have done with it.
- The **row order of the file decides nothing.** Documents are indexed in
  document-id order and ties are broken by id, on both sides — in
  ``build_rankings`` and in the percentile ranks ``rank_geometric`` reads — so
  the same distribution measured twice produces the same table. A comparison
  whose numbers move between runs cannot settle an argument about weights.

Four rows of the old table are not here and cannot be: ``max_rank``, ``rrf_60``,
``arith_rank`` and ``min_rank`` were rank-combination rules of the deleted
script. ``fuse_scores`` implements ``IMPLEMENTED_STRATEGIES`` — two rules, not
six — and routes every other string to ``weighted_norm`` without saying so, so a
rule that was measured and never shipped cannot be reproduced by asking for it
by name. They are reported as not reproducible rather than reimplemented here: a
second formula in this file is what the table's disappearance was made of.

What it does not do

It does not decide anything. Without judgments the table is empty, and with them
it is still the author's call which trade-off a review should take. It also
cannot rank a document the run never scored — a pool id with no row in the
distribution is counted and named, because no rule compared here can retrieve it
and every recall figure is depressed by it equally.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from academic_hunter.core.models.citations import citation_signal
from academic_hunter.core.nlp.fusion import (
    IMPLEMENTED_STRATEGIES,
    fuse_scores,
    resolve_weights,
)

from .qrels import doc_id_for, documents_for, topics
from .runner import build_rankings, evaluate_run

CITATION_COLUMN = "_citation_score"
DEFAULT_KS = (5, 10)
DEFAULT_TOP_K = 100

NOT_REPRODUCIBLE = (
    ("max_rank", "the better of each document's two percentile ranks"),
    ("rrf_60", "reciprocal rank fusion at k = 60"),
    ("arith_rank", "the mean of the two percentile ranks"),
    ("min_rank", "the worse of each document's two percentile ranks"),
)


@dataclass(frozen=True)
class Strategy:
    """One rule to measure, and what it needs in order to exist.

    ``signal`` ranks by one column directly — a baseline, not a fusion.
    ``strategy`` names a rule ``fuse_scores`` implements, over the signals in
    ``requires``. Those are symbolic (``sparse``, ``embedding``, ``citations``)
    and are resolved against the distribution when the comparison runs: which
    column carries the sparse signal is a property of the run, not of the rule.
    """

    label: str
    signal: str = ""
    strategy: str = ""
    weights: Optional[Dict[str, float]] = None
    requires: Tuple[str, ...] = ()


DEFAULT_STRATEGIES = (
    Strategy("run's own (Relevance_Score)", signal="Relevance_Score"),
    Strategy(
        "weighted_norm_70_30",
        strategy="weighted_norm",
        weights={"keyword": 0.7, "embedding": 0.3, "citation": 0.0},
        requires=("sparse", "embedding"),
    ),
    Strategy(
        "weighted_norm_50_50",
        strategy="weighted_norm",
        weights={"keyword": 0.5, "embedding": 0.5, "citation": 0.0},
        requires=("sparse", "embedding"),
    ),
    Strategy(
        "weighted_norm_1_0",
        strategy="weighted_norm",
        weights={"keyword": 1.0, "embedding": 0.0, "citation": 0.0},
        requires=("sparse",),
    ),
    Strategy(
        "weighted_norm_0_1",
        strategy="weighted_norm",
        weights={"keyword": 0.0, "embedding": 1.0, "citation": 0.0},
        requires=("embedding",),
    ),
    Strategy(
        "weighted_norm_cit_10",
        strategy="weighted_norm",
        weights={"keyword": 0.6, "embedding": 0.3, "citation": 0.1},
        requires=("sparse", "embedding", "citations"),
    ),
    Strategy(
        "rank_geometric",
        strategy="rank_geometric",
        requires=("sparse", "embedding"),
    ),
    Strategy("citations_baseline", signal="citations"),
)


@dataclass
class Row:
    """One rule's mean metrics, and the ordering they were computed from.

    ``rankings`` is query id to ranked document ids, kept rather than discarded
    so a reader can check the arithmetic instead of trusting it — the same
    reason ``fuse_scores`` itself is called rather than restated.
    """

    label: str
    rule: str
    metrics: Dict[str, float] = field(default_factory=dict)
    rankings: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class Result:
    """Every rule that could be measured, and every one that could not."""

    run: str
    judged_collection: str
    papers: int
    queries: int
    judged_and_scored: int
    sparse_signal: str
    citation_column: str
    citation_derived: bool
    rows: List[Row] = field(default_factory=list)
    skipped: List[Tuple[str, str]] = field(default_factory=list)
    per_topic: Dict[str, List[Row]] = field(default_factory=dict)
    unscored: List[str] = field(default_factory=list)
    duplicate_rows: int = 0
    query_details: List[Dict[str, Any]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    ks: Tuple[int, ...] = DEFAULT_KS

    @property
    def metric_columns(self) -> List[str]:
        """nDCG at each cutoff, then the two rank-independent metrics."""
        return [f"ndcg@{k}" for k in self.ks] + ["mrr", "ap"]


def load_distribution(path: Any) -> Dict[str, Any]:
    """A run's score distribution, as ``RecomputeRanksStep`` wrote it."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _as_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _citation_column(papers: Sequence[Mapping[str, Any]]) -> Tuple[str, bool]:
    """The citation column, and whether the signal had to be derived.

    ``_citation_score`` is ``citation_signal(Citations)`` as the step computed
    it, so deriving it again from the counts reproduces the same numbers — the
    repository holds one definition of citation magnitude. A run written before
    that column existed is still comparable, and the report says which of the
    two happened rather than presenting a derivation as the run's own record.
    """
    for paper in papers:
        if paper.get(CITATION_COLUMN) is not None:
            return CITATION_COLUMN, False
    return "citations", True


def _index(papers: Sequence[Mapping[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], int]:
    """Rows keyed by document id, in document-id order — one per judgment target.

    Two rows can carry one id when two records of a study share a DOI or a
    title. Ranking the paper by its worse record would lose what the better one
    qualifies for, so the copy the run scored highest wins, and two copies the
    run scored alike are settled by title so that the choice does not depend on
    which line of the file came first; the collapse is counted so that it is not
    silent.

    The order of the returned values is document id rather than file order
    because ``rank_geometric`` reads it: ``percentile_ranks`` gives tied
    documents different percentiles by position, so a row order inherited from
    the run's internal iteration would decide the ranking, and the same
    comparison run twice could disagree in the third decimal.
    """
    by_id: Dict[str, Dict[str, Any]] = {}
    collapsed = 0
    for paper in papers:
        doc_id = doc_id_for(str(paper.get("title") or ""), str(paper.get("doi") or ""))
        own = _as_float(paper.get("Relevance_Score"))
        existing = by_id.get(doc_id)
        if existing is None:
            by_id[doc_id] = {**paper, "_doc_id": doc_id, "_own_score": own}
            continue
        collapsed += 1
        better = own > existing["_own_score"] or (
            own == existing["_own_score"]
            and str(paper.get("title") or "") < str(existing.get("title") or "")
        )
        if better:
            by_id[doc_id] = {**paper, "_doc_id": doc_id, "_own_score": own}
    return by_id, collapsed


def _values(
    indexed: Sequence[Mapping[str, Any]], column: str, derived: bool
) -> List[float]:
    """One column as a list aligned with ``indexed``."""
    if derived and column == "citations":
        return [citation_signal(row.get("citations")) for row in indexed]
    return [_as_float(row.get(column)) for row in indexed]


def _rule_of(strategy: Strategy, resolved: Mapping[str, str]) -> str:
    """What a row measures, assembled from what the rule is made of."""
    if strategy.signal:
        return f"ranked by `{strategy.signal}` alone"
    signals = " + ".join(f"`{resolved[name]}`" for name in strategy.requires)
    if not strategy.weights:
        return (
            f"`{strategy.strategy}` over {signals} — the rule takes the two "
            "signals it was defined on, and no weight applies to it"
        )
    weights = "/".join(f"{value:g}" for value in strategy.weights.values())
    return f"`{strategy.strategy}` over {signals} at {weights}"


def _used_columns(strategy: Strategy, resolved: Mapping[str, str]) -> List[str]:
    """The columns the row reads, under the names this run gave them."""
    if strategy.signal:
        return [resolved["citations"] if strategy.signal == "citations" else strategy.signal]
    return [resolved[name] for name in strategy.requires]


def _constant(series: Sequence[float]) -> bool:
    return len({round(value, 9) for value in series}) < 2


def _unusable(
    strategy: Strategy,
    resolved: Mapping[str, str],
    columns: Sequence[str],
    series: Mapping[str, Sequence[float]],
) -> Optional[str]:
    """Why this row cannot be measured, or ``None`` if it can.

    Two causes, and both produce a column of numbers that reads as a result.

    A column the run never wrote is not a column of zeros: saying the embedding
    scored nothing is a different claim from saying it was never computed.

    A column that does not vary carries no ordering, and every rule here would
    have to invent one. ``weighted_norm`` would flatten it away and quietly
    measure the remaining signals under a label naming all of them — that is
    exactly what ``resolve_weights`` does to a citation weight on a corpus whose
    counts are all equal. ``rank_geometric`` is worse: ``percentile_ranks`` of a
    constant is the document's position in the input, so the row would rank by
    the caller's iteration order and look like a measurement.
    """
    used = _used_columns(strategy, resolved)
    absent = [column for column in used if column not in columns]
    if absent:
        return "this run recorded no " + ", ".join(f"`{column}`" for column in absent)

    flat = [column for column in used if _constant(series[column])]
    if not flat:
        return None

    named = ", ".join(f"`{column}`" for column in flat)
    asked = _as_float((strategy.weights or {}).get("citation"))
    if asked > 0 and resolved["citations"] in flat:
        applied = resolve_weights(strategy.weights, list(series[resolved["citations"]]))
        if applied["citation"] <= 0:
            return (
                f"`{resolved['citations']}` is constant across this run's "
                "documents, so `resolve_weights` reads the citation weight as "
                "zero: the row would measure the other signals at their ratio "
                "under a three-signal label"
            )

    return (
        f"{named} is constant across this run's documents, so it carries no "
        "ordering and this rule would have to invent one"
    )


def _scores(
    strategy: Strategy,
    resolved: Mapping[str, str],
    series: Mapping[str, Sequence[float]],
) -> List[float]:
    """One row's score per document, over the run's own stored signals."""
    if strategy.signal:
        return list(series[_used_columns(strategy, resolved)[0]])
    return fuse_scores(
        list(series[resolved["sparse"]]),
        list(series[resolved["embedding"]]),
        strategy=strategy.strategy,
        weights=strategy.weights,
        cit_scores=list(series[resolved["citations"]]),
    )


def _rank(
    by_id: Mapping[str, Mapping[str, Any]],
    score_of: Mapping[str, float],
    qrels,
    top_k: int,
) -> Dict[str, List[str]]:
    """Rank each query's own pool by one rule.

    ``build_rankings`` holds its candidate set constant across the queries it is
    given, so it is given one query at a time: two topics have two pools, and
    ranking one pool among another's documents would measure the pools instead
    of the rule. Each document is scored over the whole distribution first,
    because that is the population the run fused — a min-max normalisation over
    one 50-document pool is a different rule from the one the run applied.

    A query whose pool holds no scored document is left out rather than ranked
    empty: no rule here can serve it, and ``evaluate_run`` skips a query it was
    given no ranking for, which is what that absence means.
    """
    rankings: Dict[str, List[str]] = {}
    for query_id, judgment in qrels.queries.items():
        corpus = [
            by_id[doc_id] for doc_id in documents_for(qrels, query_id) if doc_id in by_id
        ]
        if not corpus:
            continue
        rankings.update(
            build_rankings(
                corpus,
                {query_id: judgment.text},
                scorer=lambda doc, _text: score_of[doc["_doc_id"]],
                doc_id=lambda doc: doc["_doc_id"],
                top_k=top_k,
            )
        )
    return rankings


def _measures(
    qrels,
    rankings: Mapping[str, Sequence[str]],
    query_ids: Optional[Sequence[str]],
    ks: Sequence[int],
) -> Dict[str, float]:
    """Mean metrics over a set of queries, through the shipping evaluator."""
    if query_ids is not None:
        rankings = {q: rankings[q] for q in query_ids if q in rankings}
    return dict(evaluate_run(qrels, rankings, ks=ks).mean)


def compare(
    distribution: Mapping[str, Any],
    qrels,
    top_k: int = DEFAULT_TOP_K,
    ks: Sequence[int] = DEFAULT_KS,
    strategies: Sequence[Strategy] = DEFAULT_STRATEGIES,
    judged_collection: str = "",
) -> Result:
    """Measure every rule this run's own signals can support.

    Args:
        distribution: A loaded ``score_distribution_*.json``.
        qrels: The judged collection to measure against.
        top_k: Documents kept per query — a cutoff beyond the metrics' own.
        ks: Rank cutoffs whose nDCG is reported.
        strategies: The rules to compare; defaults to the standard set.
        judged_collection: Name for the report header.

    Raises:
        ValueError: If the distribution holds no papers, or if a strategy names
            a rule ``fuse_scores`` does not implement — which would otherwise be
            measured as ``weighted_norm`` under another rule's label.
    """
    papers = [p for p in (distribution.get("papers") or []) if isinstance(p, dict)]
    if not papers:
        raise ValueError(
            "the score distribution holds no papers. Every run writes one as "
            "score_distribution_<timestamp>.json; name one that has some."
        )

    for strategy in strategies:
        if strategy.strategy and strategy.strategy not in IMPLEMENTED_STRATEGIES:
            raise ValueError(
                f"{strategy.label!r} asks for fusion strategy "
                f"{strategy.strategy!r}, which fuse_scores does not implement "
                f"({', '.join(IMPLEMENTED_STRATEGIES)}). Every other string is "
                "silently measured as weighted_norm, so the row would carry one "
                "rule's numbers under another rule's name."
            )

    ks = tuple(sorted({int(k) for k in ks if int(k) > 0})) or DEFAULT_KS
    by_id, collapsed = _index(papers)
    indexed = sorted(by_id.values(), key=lambda row: row["_doc_id"])
    columns = {key for row in indexed for key in row}
    citation_column, derived = _citation_column(indexed)
    resolved = {
        "sparse": "_bm25_score" if "_bm25_score" in columns else "_kw_score",
        "embedding": "_sem_score",
        "citations": citation_column,
    }
    details: List[Dict[str, Any]] = []
    unscored: List[str] = []
    for query_id in qrels.queries:
        pool = documents_for(qrels, query_id)
        judged = qrels.queries[query_id].grades
        missing = [doc_id for doc_id in pool if doc_id not in by_id]
        unscored.extend(missing)
        details.append(
            {
                "query_id": query_id,
                "pool": len(pool),
                "scored": len(pool) - len(missing),
                "judged": sum(1 for doc_id in pool if doc_id in judged),
                "judged_and_scored": sum(
                    1 for doc_id in pool if doc_id in judged and doc_id in by_id
                ),
            }
        )

    result = Result(
        run=str(distribution.get("run") or ""),
        judged_collection=judged_collection,
        papers=len(papers),
        queries=len(qrels.queries),
        judged_and_scored=sum(entry["judged_and_scored"] for entry in details),
        sparse_signal=resolved["sparse"],
        citation_column=citation_column,
        citation_derived=derived,
        unscored=unscored,
        duplicate_rows=collapsed,
        query_details=details,
        ks=ks,
    )

    fusion = distribution.get("fusion") or {}
    if fusion.get("strategy"):
        weights = fusion.get("weights") or {}
        applied = ", ".join(f"{name} {_as_float(value):g}" for name, value in weights.items())
        result.notes.append(
            f"the run itself fused with `{fusion['strategy']}`"
            + (f" at {applied}" if applied else "")
        )
    if fusion.get("discarded"):
        result.notes.append(
            "the run computed and then weighted zero: "
            + ", ".join(f"`{name}`" for name in fusion["discarded"])
        )

    series = {
        column: _values(indexed, column, derived)
        for column in columns | set(resolved.values())
    }

    measured: List[Tuple[Row, Dict[str, List[str]]]] = []
    for strategy in strategies:
        reason = _unusable(strategy, resolved, columns, series)
        if reason is not None:
            result.skipped.append((strategy.label, reason))
            continue
        scores = _scores(strategy, resolved, series)
        if len({round(score, 9) for score in scores}) < 2:
            result.skipped.append(
                (
                    strategy.label,
                    "every document scores the same under this rule, so its "
                    "ranking would be the tie-break rather than the rule",
                )
            )
            continue
        rankings = _rank(
            by_id, dict(zip((row["_doc_id"] for row in indexed), scores)), qrels, top_k
        )
        row = Row(
            label=strategy.label,
            rule=_rule_of(strategy, resolved),
            metrics=_measures(qrels, rankings, None, ks),
            rankings=rankings,
        )
        measured.append((row, rankings))
        result.rows.append(row)

    grouped = topics(qrels)
    if len(grouped) > 1:
        for topic, query_ids in grouped.items():
            result.per_topic[topic or "(no topic)"] = [
                Row(
                    label=row.label,
                    rule=row.rule,
                    metrics=_measures(qrels, rankings, query_ids, ks),
                    rankings=rankings,
                )
                for row, rankings in measured
            ]

    return result


def _table(result: Result, rows: Sequence[Row]) -> List[str]:
    """One markdown table: a row per rule, a column per metric."""
    head = "| Rule | " + " | ".join(
        f"nDCG@{k}" for k in result.ks
    ) + " | MRR | AP |"
    lines = [head, "| --- | " + " | ".join("---:" for _ in result.metric_columns) + " |"]
    for row in rows:
        cells = []
        for column in result.metric_columns:
            value = row.metrics.get(column)
            cells.append("—" if value is None else f"{value:.4f}")
        lines.append(f"| `{row.label}` | " + " | ".join(cells) + " |")
    return lines


def render(result: Result) -> str:
    """The comparison as a Markdown report."""
    queries = f"{result.queries} quer{'y' if result.queries == 1 else 'ies'}"
    ordered = (
        [f"# Fusion comparison — run `{result.run or 'unnamed'}`", ""]
        + [
            f"- **Papers the run evaluated:** {result.papers}",
            f"- **Judged collection:** {result.judged_collection or 'unnamed'} — "
            f"{queries}, {result.judged_and_scored} judged documents that this run "
            "scored, among the pools ranked here",
            f"- **Sparse signal:** `{result.sparse_signal}`"
            + (
                " — the run was ordered by a query, so the sparse side is BM25"
                if result.sparse_signal == "_bm25_score"
                else " — the run was not ordered by a query, so the sparse side is "
                "the domain-term score"
            ),
            f"- **Citation signal:** `{result.citation_column}`"
            + (
                " — derived here from `citations`, which is the value the step "
                "would have computed"
                if result.citation_derived
                else " — as the run recorded it"
            ),
        ]
    )

    if result.unscored:
        ordered.append(
            f"- **Pool documents with no row in the distribution:** "
            f"{len(result.unscored)} — no rule here can retrieve them, and they "
            "depress every recall figure below by the same amount"
        )
    if result.duplicate_rows:
        ordered.append(
            f"- **Rows collapsed onto one document id:** {result.duplicate_rows} "
            "— the highest-scoring copy was kept"
        )

    for note in result.notes:
        ordered.append(f"- {note}")

    if result.judged_and_scored == 0:
        ordered += [
            "",
            "## No judgments to measure against",
            "",
            "None of the pools ranked here holds a document this run both scored "
            "and had judged, so every rule would score zero for the same reason: "
            "nothing in this collection says which of these papers is relevant. "
            "Grading the pool, and measuring against the run that built it, is "
            "what makes this table mean anything.",
        ]
        return "\n".join(ordered)

    ordered += ["", "## Every rule, over the whole collection", "", *_table(result, result.rows)]

    if result.per_topic:
        ordered += [
            "",
            "## Per topic",
            "",
            "A single mean over unrelated corpora hides a rule that helps one topic "
            "and ruins another, which is the failure this breakdown exists to make "
            "visible.",
        ]
        for topic, rows in result.per_topic.items():
            if not any(row.metrics for row in rows):
                continue
            ordered += ["", f"### `{topic}`", "", *_table(result, rows)]

    ordered += ["", "## What each row is", ""]
    ordered += [f"- `{row.label}` — {row.rule}." for row in result.rows]

    if result.skipped:
        ordered += [
            "",
            "## Not measured, and why",
            "",
            "A rule left out is not a rule that scored badly. Each of these would "
            "have produced a column of numbers that described something other than "
            "the rule its label names.",
            "",
        ]
        ordered += [f"- `{label}` — {reason}." for label, reason in result.skipped]

    ordered += [
        "",
        "## Not reproducible from this repository",
        "",
        "The table this replaces also carried four rank-combination rules from a "
        "script that left with `papers/`. `fuse_scores` implements "
        f"{len(IMPLEMENTED_STRATEGIES)} rules, not six, and maps every other "
        "string to `weighted_norm` without saying so — so these cannot be "
        "measured by asking for them by name, and are named here rather than "
        "reimplemented:",
        "",
    ]
    ordered += [f"- `{name}` — {what}." for name, what in NOT_REPRODUCIBLE]
    ordered += [
        "",
        "Metrics are means over the queries, computed by `evaluate_run` with "
        "`ndcg@k` over the graded judgments. A pool document the run never scored "
        "counts as a miss for every rule alike. The table is the measurement, not "
        "the decision: which trade-off a review should take is still a judgement "
        "about the corpus, and a margin this size needs more judgments before it "
        "argues for anything.",
    ]
    return "\n".join(ordered)
