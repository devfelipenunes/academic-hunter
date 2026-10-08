"""What a citation count means, and who is accountable for it.

A count with no provenance is not evidence. The connectors report some, a
lookup answers others, and for the rest no identifier exists that any source
could be asked about — and a report that shows all three as ``0`` says the
corpus has no impact when it means it has no data. The vocabulary here is the
one place that tells them apart.
"""

import math
from typing import Any, Dict, Iterable, Sequence

REPORTED_TOKENS = frozenset({"openalex", "crossref", "core", "semantic_scholar"})
RESOLVED_TOKENS = frozenset({"openalex-doi", "crossref-doi", "doaj-doi", "openalex-batch"})
NO_IDENTIFIER = "none"
UNRESOLVED = "unresolved"

DEFAULT_IMPACT_PERCENTILE = 90.0


def citation_tokens(value: Any) -> set:
    """The provenance tokens on a paper, as a set.

    ``Citations_Source`` is merged with ``strategy_set_join``, so it arrives as a
    sorted, comma-separated list and a paper that was fetched from one source and
    completed by another carries both.
    """
    return {token.strip() for token in str(value or "").split(",") if token.strip()}


def citation_signal(citations: Any) -> float:
    """A citation count as one bounded, monotone number.

    ``log10(n + 1)`` rather than the raw count: it compresses the tail so one
    paper with a thousand citations does not flatten the rest, it keeps zero at
    zero, and it is the same transform ``AcademicScorer`` already adds to the
    keyword score, so the repository holds exactly one definition of "citation
    magnitude".
    """
    count = 0
    try:
        count = max(int(citations or 0), 0)
    except (TypeError, ValueError):
        count = 0
    return round(math.log10(count + 1), 4)


def _field(paper: Dict[str, Any], canonical: str, lower: str) -> Any:
    """A paper field, under either spelling.

    Papers carry the schema's field names; the score-distribution sidecar writes
    its columns in lower case. Both are read here so the same summary describes
    the collection and the artifact written from it, and the two cannot drift.
    """
    if canonical in paper:
        return paper.get(canonical)
    return paper.get(lower)


def citation_summary(papers: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    """How many papers carry a count, and where each count came from.

    The buckets are disjoint and cover every paper, so the report's coverage line
    adds up to the population it describes. A zero with a reporting token behind
    it is a source that answered zero; a zero with no token at all is a paper
    nobody asked, which is what a disabled backfill leaves behind.
    """
    summary = {
        "papers": 0,
        "with_count": 0,
        "reported": 0,
        "resolved": 0,
        "confirmed_zero": 0,
        "unresolved": 0,
        "without_identifier": 0,
        "not_asked": 0,
    }
    for paper in papers:
        summary["papers"] += 1
        tokens = citation_tokens(_field(paper, "Citations_Source", "citations_source"))
        try:
            citations = int(_field(paper, "Citations", "citations") or 0)
        except (TypeError, ValueError):
            citations = 0
        if citations:
            summary["with_count"] += 1
            if tokens & RESOLVED_TOKENS:
                summary["resolved"] += 1
            else:
                summary["reported"] += 1
        elif UNRESOLVED in tokens:
            summary["unresolved"] += 1
        elif NO_IDENTIFIER in tokens:
            summary["without_identifier"] += 1
        elif tokens & (REPORTED_TOKENS | RESOLVED_TOKENS):
            summary["confirmed_zero"] += 1
        else:
            summary["not_asked"] += 1
    return summary


def impact_cutoff(citations: Sequence[int], percentile: Any = None) -> float:
    """The count that separates the run's most-cited papers from the rest.

    Derived from the distribution the run actually produced rather than fixed in
    advance, for the same reason the inclusion predicate is declared: a number
    chosen by hand would be a preference, and the report has to be able to say
    where the line fell and how many papers were above it. Zero-citation papers
    are excluded from the percentile, or a corpus that is mostly zeros would put
    the line at zero and call every cited paper an outlier.
    """
    values = []
    for value in citations:
        try:
            number = int(value or 0)
        except (TypeError, ValueError):
            continue
        if number > 0:
            values.append(number)
    if not values:
        return 0.0
    try:
        share = float(percentile)
    except (TypeError, ValueError):
        share = DEFAULT_IMPACT_PERCENTILE
    share = min(max(share, 0.0), 100.0)
    values.sort()
    position = min(int(share / 100.0 * (len(values) - 1)), len(values) - 1)
    return float(values[position])
