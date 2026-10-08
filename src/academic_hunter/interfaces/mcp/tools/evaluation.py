"""MCP tools for measuring retrieval quality instead of asserting it.

Accepts a ``ctx: Context`` parameter (auto-injected by FastMCP) for logging and
progress reporting.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from academic_hunter.core.evaluation import (
    Calibration,
    QrelsError,
    load_qrels,
    sweep_threshold,
)
from academic_hunter.core.evaluation.comparison import (
    DEFAULT_KS,
    DEFAULT_STRATEGIES,
    DEFAULT_TOP_K,
    compare,
    render,
)
from academic_hunter.core.infra import paths
from mcp.server.fastmcp import Context

from ..exceptions import SearchError
from ._utils import get_project_root, run_blocking

logger = logging.getLogger("academic_hunter.mcp.evaluation")


def _distribution_path(run: str) -> Optional[Path]:
    """The score distribution of the named run, or of the most recent one.

    The sidecar is written next to the run's other artifacts, so an empty ``run``
    means the newest ``score_distribution_*.json`` under the results directory.
    """
    results_dir = get_project_root() / paths.RESULTS_DIRNAME
    pattern = f"score_distribution_*{run}*.json" if run else "score_distribution_*.json"
    candidates = list(results_dir.rglob(pattern))
    if not candidates:
        return None
    stamped = [p for p in candidates if p.name != "score_distribution_.json"]
    if not stamped:
        return None
    return max(stamped, key=lambda path: path.name)


def _load_distribution(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _available_qrels() -> List[str]:
    """Judged collections in the repository, with what each one holds.

    Offered rather than picked. The files in ``evaluation/`` judge different
    topics, and calibrating one review's threshold against another review's
    judgments would produce a confident number that means nothing.
    """
    lines = []
    for path in sorted((get_project_root() / "evaluation").glob("*.json")):
        try:
            qrels = load_qrels(path)
        except QrelsError:
            continue
        lines.append(
            f"- `{path.relative_to(get_project_root())}` — {len(qrels)} queries, "
            f"{qrels.n_judgments} judgments, {qrels.n_relevant} relevant"
            + (f" ({qrels.description})" if qrels.description else "")
        )
    if not lines:
        return ["No judged collection found under `evaluation/`."]
    return lines


def _render_table(rows, recommended, current, max_steps: int) -> str:
    """The candidate thresholds, thinned from the middle if there are many.

    Thinned rather than truncated: the recommendation can sit anywhere in the
    range, and a table that stopped at the first ``max_steps`` rows would hide
    the very threshold it recommends.
    """
    if len(rows) > max_steps:
        step = (len(rows) - 1) / (max_steps - 1)
        keep = {int(round(i * step)) for i in range(max_steps)}
        keep.add(rows.index(recommended) if recommended in rows else 0)
        rows = [row for i, row in enumerate(rows) if i in keep]

    lines = [
        "| Threshold | Included | Judged | Precision | Precision (floor) | Recall | F1 |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        marks = []
        if recommended is not None and row.threshold == recommended.threshold:
            marks.append("**recommended**")
        if current is not None and row.threshold == current.threshold:
            marks.append("run's own")
        suffix = f" ← {', '.join(marks)}" if marks else ""
        lines.append(
            f"| {row.threshold:g}{suffix} | {row.included} | {row.judged} | "
            f"{row.precision:.2f} | {row.precision_floor:.2f} | {row.recall:.2f} | "
            f"{row.f1:.2f} |"
        )
    return "\n".join(lines)


def _render(
    calibration: Calibration,
    distribution: Dict[str, Any],
    recommended,
    target_precision: float,
    max_steps: int,
) -> str:
    current_value = distribution.get("min_inclusion_score")
    current = (
        calibration.row_for(float(current_value)) if current_value is not None else None
    )

    out = [
        f"# Threshold calibration — `{calibration.key}`",
        "",
        f"- **Run:** {distribution.get('run')}",
        f"- **Predicate as applied:** `{distribution.get('inclusion_predicate')}`",
        f"- **Papers evaluated:** {calibration.evaluated} "
        f"({calibration.judged} of them carry a judgment)",
        f"- **Judged relevant in the collection:** {calibration.n_relevant}, of which "
        f"{calibration.n_relevant_evaluated} were evaluated by this run "
        f"({calibration.missed_by_retrieval} were never collected, so no threshold "
        f"can admit them)",
        "",
    ]

    if recommended is None:
        out += [
            "## No threshold can be recommended",
            "",
            "None of the candidates has a judged paper in its included set, so there "
            "is no precision to measure. Judging a sample of this run's papers is "
            "what makes a calibration possible.",
        ]
        return "\n".join(out)

    out += [
        "## Recommendation",
        "",
        f"Set `settings.min_inclusion_score` to **{recommended.threshold:g}**.",
        "",
        f"- Admits **{recommended.included}** papers, **{recommended.relevant}** of them "
        f"judged relevant, out of {calibration.n_relevant_evaluated} judged-relevant "
        f"papers this run evaluated.",
        f"- Precision **{recommended.precision:.2f}** over the "
        f"{recommended.judged} included papers that were judged; between "
        f"{recommended.precision_floor:.2f} and {recommended.precision:.2f} overall, "
        f"since {recommended.coverage:.0%} of the included set was judged.",
        f"- Recall **{recommended.recall:.2f}** of the judged-relevant papers the run "
        f"collected.",
    ]
    if target_precision > 0:
        out.append(
            f"- Chosen as the lowest threshold reaching a precision of "
            f"{target_precision:g}; among those it keeps the most papers, because "
            f"recall is what a review cannot recover later."
        )
    else:
        out.append(
            "- Chosen by F1, which weighs precision and recall equally. Pass "
            "`target_precision` to trade recall for precision deliberately."
        )
    out.append("")

    if current is not None:
        out += [
            "## Against the run's own threshold",
            "",
            f"The run used **{current.threshold:g}** and admitted {current.included} "
            f"papers at a precision of {current.precision:.2f} and a recall of "
            f"{current.recall:.2f}. Moving to the recommendation changes the included "
            f"set by {recommended.included - current.included} papers.",
            "",
        ]

    out += [
        "## The sweep",
        "",
        _render_table(calibration.rows, recommended, current, max_steps),
        "",
        "Precision is measured on the judged papers in the included set; the floor "
        "column counts every unjudged paper as not relevant, so the true value lies "
        "between the two. Recall is over the judged-relevant papers this run "
        "evaluated — a threshold cannot admit a paper the search never collected.",
    ]
    return "\n".join(out)


async def calibrate_inclusion_threshold(
    ctx: Context,
    qrels_path: str = "",
    run: str = "",
    target_precision: float = 0.0,
    max_steps: int = 25,
) -> str:
    """Chooses the inclusion threshold with precision and recall, not with taste.

    Sweeps `settings.min_inclusion_score` across the papers a run actually
    evaluated — included and excluded alike, as recorded in that run's
    `score_distribution_<timestamp>.json` — and scores each candidate against a
    judged collection. The threshold decides what the review contains, and until
    this existed the run evicted everything below it before exporting, so the
    population the choice was about could not be inspected at all.

    Precision is reported as a range: judgments cover only part of any run, and
    the tool says what share of the included set it rests on. Recall is measured
    over the judged-relevant papers this run collected; a paper the search never
    found is not a threshold's failure, and the count of those is reported
    separately.

    Args:
        ctx: FastMCP Context (auto-injected).
        qrels_path: Path to the judged collection, relative to the project root.
            Omit it to list the ones available — each judges a different topic,
            and calibrating one review against another's judgments would produce
            a confident number that means nothing.
        run: Run timestamp to calibrate, e.g. ``"20261006_131059"``. Defaults to
            the most recent run that wrote a score distribution.
        target_precision: If above 0, recommend the lowest threshold whose
            precision reaches it, keeping the most papers subject to that floor.
            Otherwise recommend the best F1.
        max_steps: How many candidate thresholds to show. The recommendation is
            always shown.
    """
    try:
        if not qrels_path:
            available = await run_blocking(_available_qrels)
            return (
                "Name the judged collection to measure against, with `qrels_path`:\n\n"
                + "\n".join(available)
            )

        qrels_file = Path(qrels_path)
        if not qrels_file.is_absolute():
            qrels_file = get_project_root() / qrels_file

        path = await run_blocking(_distribution_path, run)
        if path is None:
            return (
                "No score distribution found"
                + (f" for run `{run}`" if run else "")
                + ". It is written by every run into its own directory as "
                "`score_distribution_<timestamp>.json`; run a search first, or "
                "name a run that has one."
            )

        await ctx.info(f"Calibrating against {qrels_file} over {path.name}")

        distribution = await run_blocking(_load_distribution, path)
        papers = distribution.get("papers") or []
        if not papers:
            return f"{path} holds no papers to sweep."

        qrels = await run_blocking(load_qrels, qrels_file)
        calibration = await run_blocking(
            sweep_threshold,
            papers,
            qrels,
            distribution.get("inclusion_key", "_kw_score"),
            None,
            max_steps,
        )
        recommended = calibration.recommend(target_precision or None)

        return _render(calibration, distribution, recommended, target_precision, max_steps)

    except QrelsError as e:
        await ctx.error(f"Judged collection could not be read: {e}")
        return f"That judged collection could not be read: {e}"
    except SearchError:
        raise
    except Exception as e:
        await ctx.error(f"Threshold calibration failed: {e}")
        raise SearchError(str(e))


async def compare_fusion_weights(
    ctx: Context,
    qrels_path: str = "",
    run: str = "",
) -> str:
    """Measures the fusion rules against the judgments, so weights are a decision.

    `calibrate_inclusion_threshold` chooses the cut with numbers behind it and
    leaves the weights — which decide the ordering that cut is applied to —
    to taste. This measures them: it re-fuses a run's own stored signals under
    each rule in turn and scores the resulting rankings against a judged
    collection, so ``keyword``/``embedding``/``citation`` can be argued about.

    It calls the module that ships (`core/nlp/fusion.py`) rather than restating
    the formula, and it says which signals it read: the sparse side is `_bm25_score`
    when the run had a `ranking_query` and `_kw_score` when it did not, and the
    citation column is derived from the counts when the run did not record one.
    A run ordered by nobody's query is not comparable to one ordered by a query,
    and the report names which this is.

    A rule is left out and named with its reason rather than shown as a row of
    numbers when either column it would read is missing from the run, or does not
    vary across its documents: absent and bad look identical in a table, a
    constant column gives every rule a way to invent an ordering out of the input
    order, and a citation weight the fusion reads as zero — because the counts do
    not vary — would be measured under a three-signal label. Four rows of the
    table this replaces are named as not reproducible: it was measured by a
    script that left the repository, and its rank-combination rules were never in
    `fuse_scores`, so asking for them by name would silently measure
    `weighted_norm` instead.

    Args:
        ctx: FastMCP Context (auto-injected).
        qrels_path: Path to the judged collection, relative to the project root.
            Omit it to list the ones available — each judges a different topic,
            and measuring one review against another's judgments produces a
            table of numbers that describe neither.
        run: Run timestamp whose score distribution to measure, e.g.
            ``"20261006_131059"``. Defaults to the most recent run that wrote one.
            The collection has to judge the same topic as that run: the pool ids
            are the join between the two, and the report counts the documents it
            could not match rather than scoring them as misses it cannot see.
    """
    try:
        if not qrels_path:
            available = await run_blocking(_available_qrels)
            return (
                "Name the judged collection to measure against, with `qrels_path`:\n\n"
                + "\n".join(available)
            )

        qrels_file = Path(qrels_path)
        if not qrels_file.is_absolute():
            qrels_file = get_project_root() / qrels_file

        path = await run_blocking(_distribution_path, run)
        if path is None:
            return (
                "No score distribution found"
                + (f" for run `{run}`" if run else "")
                + ". Every run writes one into its own directory as "
                "`score_distribution_<timestamp>.json`; run a search first, or "
                "name a run that has one."
            )

        await ctx.info(f"Comparing fusion rules over {path.name} against {qrels_file}")

        distribution = await run_blocking(_load_distribution, path)
        qrels = await run_blocking(load_qrels, qrels_file)
        result = await run_blocking(
            compare,
            distribution,
            qrels,
            DEFAULT_TOP_K,
            DEFAULT_KS,
            DEFAULT_STRATEGIES,
            qrels_path,
        )
        return render(result)

    except QrelsError as e:
        await ctx.error(f"Judged collection could not be read: {e}")
        return f"That judged collection could not be read: {e}"
    except ValueError as e:
        await ctx.error(f"Nothing to compare: {e}")
        return f"That comparison cannot be made: {e}"
    except SearchError:
        raise
    except Exception as e:
        await ctx.error(f"Fusion comparison failed: {e}")
        raise SearchError(str(e))
