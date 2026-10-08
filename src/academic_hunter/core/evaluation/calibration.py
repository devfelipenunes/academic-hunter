"""Choose the inclusion threshold from measurements instead of taste.

The threshold decides what the review contains, and until now it was a number in
a configuration file with nothing behind it: the run evicted every paper below
the cut before exporting, so the population the choice was about was gone by the
time anyone could look at it. ``RecomputeRanksStep`` now writes every evaluated
paper's signals to ``score_distribution_<timestamp>.json``, and this sweeps the
cut across those papers, scoring each position against a judged collection.

What it cannot invent is judgments. Precision here is measured on the papers the
qrels actually judged, so it is a bound and not a fact: ``precision`` treats the
unjudged papers in the included set as unknown, ``precision_floor`` treats them
as not relevant, and the true value lies between the two. Both are reported with
the number of judged papers they rest on, because a precision over three
judgments is not a measurement.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from .qrels import RELEVANT_THRESHOLD, Qrels, doc_id_for


@dataclass(frozen=True)
class Sweep:
    """What one candidate threshold would do to the review."""

    threshold: float
    included: int
    judged: int
    relevant: int
    precision: float
    precision_floor: float
    recall: float
    f1: float
    coverage: float

    def as_dict(self) -> Dict[str, Any]:
        return {
            "threshold": self.threshold,
            "included": self.included,
            "judged": self.judged,
            "relevant": self.relevant,
            "precision": round(self.precision, 4),
            "precision_floor": round(self.precision_floor, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "coverage": round(self.coverage, 4),
        }


@dataclass
class Calibration:
    """A sweep over one run's evaluated papers, and what it recommends."""

    key: str
    evaluated: int
    judged: int
    n_relevant: int
    n_relevant_evaluated: int
    rows: List[Sweep] = field(default_factory=list)

    @property
    def missed_by_retrieval(self) -> int:
        """Judged-relevant papers this run never collected.

        No threshold can admit them, so they are outside what the sweep
        measures -- counting them as a threshold's failure would blame the cut
        for the search.
        """
        return self.n_relevant - self.n_relevant_evaluated

    def row_for(self, threshold: float) -> Optional[Sweep]:
        """The row closest to a threshold, for comparing against the run's own."""
        if not self.rows:
            return None
        return min(self.rows, key=lambda row: abs(row.threshold - threshold))

    def recommend(self, target_precision: Optional[float] = None) -> Optional[Sweep]:
        """The threshold worth using, or None when nothing can be measured.

        With a precision target, it is the **lowest** threshold that meets it:
        recall is the thing a review cannot recover later, so among the
        thresholds that are precise enough the one that admits the most papers
        wins. Without a target it is the best F1, which weights the two equally.

        A position where nothing in the included set was judged has no precision
        to offer and is passed over rather than recommended on a sample of zero.
        """
        measurable = [row for row in self.rows if row.judged > 0]
        if not measurable:
            return None
        if target_precision is None:
            return max(measurable, key=lambda row: (row.f1, row.recall, -row.threshold))
        meeting = [row for row in measurable if row.precision >= target_precision]
        if not meeting:
            return None
        return min(meeting, key=lambda row: row.threshold)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "evaluated": self.evaluated,
            "judged": self.judged,
            "n_relevant": self.n_relevant,
            "n_relevant_evaluated": self.n_relevant_evaluated,
            "missed_by_retrieval": self.missed_by_retrieval,
            "rows": [row.as_dict() for row in self.rows],
        }


def candidate_thresholds(values: Iterable[float], limit: int = 40) -> List[float]:
    """The thresholds worth testing: the papers' own scores, thinned to ``limit``.

    The count of included papers only changes where a score crosses the
    threshold, so the candidates are those scores. A grid would report many
    thresholds that decide nothing and can step over the value that matters. A
    run wide enough to make the list unwieldy is thinned by index rather than by
    value, so the whole range stays visible instead of the dense head crowding
    out the tail. Zero is always a candidate: it is what "include everything the
    screening passed" means.
    """
    distinct = sorted({float(value) for value in values})
    if not distinct:
        return [0.0]

    candidates = [0.0] + [v for v in distinct if v > 0.0]
    if limit <= 0 or len(candidates) <= limit:
        return candidates

    step = (len(candidates) - 1) / (limit - 1)
    thinned = [candidates[int(round(i * step))] for i in range(limit)]
    return sorted(set(thinned))


def index_documents(papers: Sequence[Mapping[str, Any]], key: str) -> Dict[str, float]:
    """Document id -> best score, one entry per judgment target.

    Two rows can carry one id when two records of a study share its DOI or
    title: counting the pair twice would double a judgment's weight in the
    precision, and keeping the lower score would exclude a paper whose better
    copy qualifies.
    """
    best: Dict[str, float] = {}
    for paper in papers:
        doc_id = doc_id_for(str(paper.get("title", "") or ""), str(paper.get("doi", "") or ""))
        try:
            value = float(paper.get(key) or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        if doc_id not in best or value > best[doc_id]:
            best[doc_id] = value
    return best


def sweep_threshold(
    papers: Sequence[Mapping[str, Any]],
    qrels: Qrels,
    key: str = "_kw_score",
    thresholds: Optional[Sequence[float]] = None,
    limit: int = 40,
) -> Calibration:
    """Score every candidate threshold against the judged collection.

    Args:
        papers: Rows of a run's score distribution, each with ``title``,
            ``doi`` and the signal named by ``key``.
        qrels: The judgments to measure against.
        key: The signal the threshold is applied to.
        thresholds: Candidates; derived from the papers when omitted.
        limit: How many candidates to derive when none are given.

    Returns:
        A :class:`Calibration` whose rows are ordered by threshold.
    """
    scores = index_documents(papers, key)
    grades: Dict[str, int] = {}
    for judgment in qrels.queries.values():
        for doc_id, grade in judgment.grades.items():
            grades[doc_id] = max(grades.get(doc_id, 0), grade)

    relevant_ids = {d for d, g in grades.items() if g >= RELEVANT_THRESHOLD}
    evaluated_relevant = relevant_ids & set(scores)

    if thresholds is None:
        thresholds = candidate_thresholds(scores.values(), limit=limit)

    denominator = len(evaluated_relevant)
    rows: List[Sweep] = []
    for threshold in sorted({float(t) for t in thresholds}):
        included = [d for d, value in scores.items() if value >= threshold]
        judged = [d for d in included if d in grades]
        relevant = [d for d in judged if grades[d] >= RELEVANT_THRESHOLD]
        precision = len(relevant) / len(judged) if judged else 0.0
        floor = len(relevant) / len(included) if included else 0.0
        recall = len(relevant) / denominator if denominator else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        rows.append(
            Sweep(
                threshold=threshold,
                included=len(included),
                judged=len(judged),
                relevant=len(relevant),
                precision=precision,
                precision_floor=floor,
                recall=recall,
                f1=f1,
                coverage=len(judged) / len(included) if included else 0.0,
            )
        )

    return Calibration(
        key=key,
        evaluated=len(scores),
        judged=sum(1 for d in scores if d in grades),
        n_relevant=len(relevant_ids),
        n_relevant_evaluated=denominator,
        rows=rows,
    )
