"""The judged-collection format.

A qrels file records, for each query, which documents a human judged relevant
and how relevant. It is the ground truth the metrics score against, so the
format is deliberately explicit and reviewable by hand.

Shape::

    {
      "description": "...",
      "queries": {
        "q1": {
          "text": "query string, or a description of the information need",
          "judgments": {"doc-id-a": 2, "doc-id-b": 1, "doc-id-c": 0}
        }
      }
    }

Document ids must be stable and derivable from a paper — :func:`doc_id_for` is
the canonical helper so a qrels entry can be matched to a corpus row.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Union

#: Grades at or above this are "relevant"; anything below is not.
RELEVANT_THRESHOLD = 1


class QrelsError(ValueError):
    """Raised when a qrels file is malformed."""


@dataclass
class Judgment:
    """One query's relevance grades."""

    query_id: str
    text: str
    grades: Dict[str, int] = field(default_factory=dict)
    #: Informational grouping, e.g. ``genre_analysis``. Lets a report show
    #: per-topic means instead of one number over unrelated corpora.
    topic: str = ""
    #: The documents this query was judged over. Rankings are built within a
    #: pool, so a query from one topic is never scored against another topic's
    #: documents — those are unjudged for it, and counting them as irrelevant
    #: would penalise a ranker for a pool it was never given. Empty means "the
    #: whole judged collection", which is what single-topic files want.
    pool: List[str] = field(default_factory=list)

    @property
    def relevant_ids(self) -> list:
        """Ids judged relevant, i.e. graded at or above the threshold."""
        return [d for d, g in self.grades.items() if g >= RELEVANT_THRESHOLD]

    def __len__(self) -> int:
        return len(self.grades)


@dataclass
class Qrels:
    """A judged collection: queries plus their relevance grades."""

    queries: Dict[str, Judgment] = field(default_factory=dict)
    description: str = ""

    def __len__(self) -> int:
        return len(self.queries)

    def __iter__(self):
        return iter(self.queries.values())

    def __getitem__(self, query_id: str) -> Judgment:
        return self.queries[query_id]

    @property
    def n_judgments(self) -> int:
        """Total graded (query, document) pairs."""
        return sum(len(j) for j in self.queries.values())

    @property
    def n_relevant(self) -> int:
        return sum(len(j.relevant_ids) for j in self.queries.values())

    def stats(self) -> Dict[str, Any]:
        """Summary suitable for a report header."""
        return {
            "queries": len(self),
            "judgments": self.n_judgments,
            "relevant": self.n_relevant,
            "description": self.description,
        }


def doc_id_for(title: str = "", doi: str = "") -> str:
    """Canonical document id for a paper.

    Prefers the DOI (stable across sources), falling back to a normalised title
    slug. Uses the same slug rule as ``AcademicScorer.generate_slug`` so that an
    id derived here matches one derived by the pipeline.
    """
    doi_clean = (doi or "").strip().lower()
    if doi_clean:
        return f"doi:{doi_clean}"
    return f"title:{re.sub(r'\W+', '', str(title).lower())}"


def load_qrels(path: Union[str, Path]) -> Qrels:
    """Load and validate a qrels JSON file.

    Raises:
        QrelsError: If the file is missing, is not valid JSON, or has entries
            that would silently score as zero (negative grades, non-integer
            grades, an empty query list).
    """
    path = Path(path)
    if not path.exists():
        raise QrelsError(f"qrels file not found: {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise QrelsError(f"{path} is not valid JSON: {e}") from e

    if not isinstance(raw, dict):
        raise QrelsError(f"{path}: top level must be an object")

    queries_raw = raw.get("queries")
    if not isinstance(queries_raw, dict) or not queries_raw:
        raise QrelsError(f"{path}: 'queries' must be a non-empty object")

    qrels = Qrels(description=str(raw.get("description", "")))

    for query_id, entry in queries_raw.items():
        if not isinstance(entry, dict):
            raise QrelsError(f"{path}: query {query_id!r} must be an object")

        grades_raw = entry.get("judgments", {})
        if not isinstance(grades_raw, dict):
            raise QrelsError(f"{path}: query {query_id!r} 'judgments' must be an object")

        grades: Dict[str, int] = {}
        for doc_id, grade in grades_raw.items():
            if isinstance(grade, bool) or not isinstance(grade, int):
                raise QrelsError(
                    f"{path}: query {query_id!r} doc {doc_id!r} grade must be an "
                    f"integer, got {grade!r}. Quote it, or drop the entry — a "
                    f"silently unparsed grade scores as not relevant."
                )
            if grade < 0:
                raise QrelsError(
                    f"{path}: query {query_id!r} doc {doc_id!r} has negative grade {grade}"
                )
            grades[str(doc_id)] = grade

        qrels.queries[str(query_id)] = Judgment(
            query_id=str(query_id),
            text=str(entry.get("text", "")),
            grades=grades,
            topic=str(entry.get("topic", "")),
            pool=[str(d) for d in (entry.get("pool") or [])],
        )

    return qrels


def documents_for(qrels: Qrels, query_id: str) -> List[str]:
    """The documents to rank for one query.

    Returns the query's declared pool, or — when it declares none — every
    document that carries a judgment anywhere in the collection, sorted for
    deterministic ordering. The fallback keeps single-topic files (which have no
    pools) working exactly as before.
    """
    if query_id not in qrels.queries:
        raise QrelsError(f"unknown query id: {query_id}")

    pool = qrels.queries[query_id].pool
    if pool:
        return list(pool)
    return sorted(pooled_documents(qrels))


def topics(qrels: Qrels) -> Dict[str, List[str]]:
    """Query ids grouped by their ``topic``, in first-seen order.

    Queries without a topic land under ``""``.
    """
    grouped: Dict[str, List[str]] = {}
    for query_id, judgment in qrels.queries.items():
        grouped.setdefault(judgment.topic, []).append(query_id)
    return grouped


def save_qrels(qrels: Qrels, path: Union[str, Path]) -> Path:
    """Write a qrels collection back to disk, sorted for stable diffs."""
    path = Path(path)
    payload = {
        "description": qrels.description,
        "queries": {
            qid: {
                "text": j.text,
                # Omitted when unset, so single-topic files keep their old shape
                # and a diff stays readable.
                **({"topic": j.topic} if j.topic else {}),
                **({"pool": list(j.pool)} if j.pool else {}),
                "judgments": dict(sorted(j.grades.items())),
            }
            for qid, j in sorted(qrels.queries.items())
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def relevance_map(qrels: Qrels, query_id: str) -> Mapping[str, int]:
    """Grades for one query, as the mapping the metrics expect."""
    if query_id not in qrels.queries:
        raise QrelsError(f"unknown query id: {query_id}")
    return qrels.queries[query_id].grades


def pooled_documents(qrels: Qrels) -> set:
    """Every document id that appears in any judgment."""
    out: set = set()
    for j in qrels.queries.values():
        out |= set(j.grades)
    return out
