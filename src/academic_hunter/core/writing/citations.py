"""Citation verification.

Verification runs in three layers, cheapest first:

1. **Existence** — deterministic. Does the reference exist at all: is the key in
   the bibliography, does the DOI resolve, is the paper in the local corpus?
   This is the layer that eliminates fabricated citations, which the literature
   puts at 20-50% of LLM-generated references (and 78-90% for one widely tested
   model).
2. **Support** — does the cited paper actually back the claim it is attached to?
3. **Numbers** — do the figures quoted in the text match the result files?

This module owns layer 1 and the extraction shared by all three. It is pure:
bibliography, DOI resolution and corpus lookup arrive as injected callables, so
the logic is testable with no network, no corpus and no model.
"""

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional

from ._text import sentence_around

_CITATION = re.compile(r"\[@([^\]]+)\]")
_KEY_SPLIT = re.compile(r"\s*;\s*")

VERDICT_VERIFIED = "VERIFIED"
VERDICT_NOT_FOUND = "NOT_FOUND"
VERDICT_UNKNOWN = "UNKNOWN"


@dataclass
class CitationCandidate:
    """A citation found in a text, with the sentence it sits in."""

    key: str
    context: str
    offset: int


@dataclass
class ExistenceResult:
    """Layer-1 outcome for one citation."""

    key: str
    context: str
    in_bibliography: Optional[bool] = None
    doi_resolves: Optional[bool] = None
    in_corpus: Optional[bool] = None
    verdict: str = VERDICT_UNKNOWN
    evidence: str = ""

    def as_dict(self) -> Dict[str, object]:
        return {
            "key": self.key,
            "verdict": self.verdict,
            "in_bibliography": self.in_bibliography,
            "doi_resolves": self.doi_resolves,
            "in_corpus": self.in_corpus,
            "evidence": self.evidence,
        }


def extract_citations(text: str) -> List[CitationCandidate]:
    """Find every ``[@key]`` citation in a text, with its surrounding sentence.

    Returns one candidate per key — a multi-key citation ``[@a; @b]`` yields two,
    because each must be verified independently.

    A Pandoc locator is dropped: ``[@k, p. 33]`` cites ``k``. Keeping the comma
    and what followed it made the key ``k, p. 33``, which no bibliography holds,
    so a correctly cited page was reported as a fabricated reference.
    """
    candidates: List[CitationCandidate] = []
    for match in _CITATION.finditer(text):
        context = sentence_around(text, match.start())
        for raw in _KEY_SPLIT.split(match.group(1)):
            key = raw.split(",")[0].strip().lstrip("@").strip()
            if key:
                candidates.append(
                    CitationCandidate(key=key, context=context, offset=match.start())
                )
    return candidates


@dataclass
class ExistenceProbes:
    """The lookups layer 1 needs, injected.

    Probes come in two kinds, and the distinction matters:

    - **Refuting** — a negative answer proves the reference does not exist.
      Absence from the bibliography the manuscript cites, or a DOI that does not
      resolve, are genuine defects.
    - **Confirming** — a positive answer proves it does exist, but a negative
      answer proves nothing. The local corpus is a *subset* of the literature:
      a paper can be entirely real and simply not indexed here, so failing to
      find it is not evidence against it. Treating it as refuting produced a
      30-of-30 false-positive rate when first run against a real manuscript.

    Every callable returns a bool when it can decide, or ``None`` when the
    question is out of scope (no bibliography supplied, no DOI recorded). A
    ``None`` never counts as a failure.
    """

    in_bibliography: Optional[Callable[[str], Optional[bool]]] = None
    doi_resolves: Optional[Callable[[str], Optional[bool]]] = None
    in_corpus: Optional[Callable[[str], Optional[bool]]] = None
    resolve_doi: Optional[Callable[[str], Optional[str]]] = None
    field: Dict[str, object] = field(default_factory=dict)


def verify_existence(
    candidates: Iterable[CitationCandidate],
    probes: ExistenceProbes,
) -> List[ExistenceResult]:
    """Run layer 1 over a list of citations.

    Verdict logic:
    - **NOT_FOUND** when a *refuting* probe answers negatively — the reference
      is provably absent.
    - **VERIFIED** when at least one probe confirms it and none refutes.
    - **UNKNOWN** when nothing could be decided. Never reported as a failure:
      "we could not check" and "this is fabricated" are different claims, and
      conflating them is how a verifier loses its credibility.
    """
    results: List[ExistenceResult] = []

    for candidate in candidates:
        result = ExistenceResult(key=candidate.key, context=candidate.context)
        confirmed_by: List[str] = []

        if probes.in_bibliography is not None:
            answer = probes.in_bibliography(candidate.key)
            result.in_bibliography = answer
            if answer is False:
                result.verdict = VERDICT_NOT_FOUND
                result.evidence = f"'{candidate.key}' is not in the bibliography"
                results.append(result)
                continue
            if answer is True:
                confirmed_by.append("bibliography")

        doi: Optional[str] = None
        if probes.resolve_doi is not None:
            doi = probes.resolve_doi(candidate.key)

        if probes.doi_resolves is not None and doi:
            answer = probes.doi_resolves(doi)
            result.doi_resolves = answer
            if answer is False:
                result.verdict = VERDICT_NOT_FOUND
                result.evidence = f"DOI {doi} does not resolve"
                results.append(result)
                continue
            if answer is True:
                confirmed_by.append("DOI")

        if probes.in_corpus is not None:
            answer = probes.in_corpus(candidate.key)
            result.in_corpus = answer
            if answer is True:
                confirmed_by.append("corpus")

        if confirmed_by:
            result.verdict = VERDICT_VERIFIED
            result.evidence = "confirmed by " + ", ".join(confirmed_by)
        else:
            result.verdict = VERDICT_UNKNOWN
            result.evidence = "no probe could decide — nothing to check against"

        results.append(result)

    return results


_ENTRY_START = re.compile(r"@(\w+)\s*(\{)\s*([^,\s]+)\s*,")
_FIELD_START = re.compile(r"(\w+)\s*=\s*")


def _balanced(text: str, start: int) -> tuple[str, int]:
    """The content of the braced group opening at ``start``, and where it ends."""
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:index], index + 1
    return text[start + 1:], len(text)


def _read_value(body: str, start: int) -> tuple[str, int]:
    """One field value, up to whatever closes it, and the position after it."""
    if start >= len(body):
        return "", start
    opener = body[start]
    if opener == "{":
        return _balanced(body, start)
    if opener == '"':
        end = body.find('"', start + 1)
        return (body[start + 1:end], end + 1) if end != -1 else (body[start + 1:], len(body))
    end = start
    while end < len(body) and body[end] not in ",\n":
        end += 1
    return body[start:end], end


def _parse_fields(body: str) -> Dict[str, str]:
    """Read ``name = value`` pairs, skipping over each value once read.

    Scanning with a regex alone would find the ``=`` inside a value and read the
    words around it as a field, so every value's span is stepped over whole.
    """
    fields: Dict[str, str] = {}
    position = 0
    for match in _FIELD_START.finditer(body):
        if match.start() < position:
            continue
        value, position = _read_value(body, match.end())
        fields[match.group(1).lower()] = " ".join(value.split())
    return fields


def parse_bibtex_keys(bibtex: str) -> set[str]:
    """Extract entry keys from BibTeX content.

    Deliberately a regex rather than a full parser: it only needs to answer
    "does this key exist", and pulling in a parse dependency for that would be
    a heavier contract than the layer requires.
    """
    return set(re.findall(r"@\w+\s*\{\s*([^,\s]+)\s*,", bibtex))


def parse_bibtex_entries(bibtex: str) -> Dict[str, Dict[str, str]]:
    """Parse BibTeX into ``{key: {field: value}}``.

    Intentionally shallow: layer 1 only needs the key, its DOI and its title in
    order to check that a reference exists. Values are flattened to one line and
    no macro, ``@string`` or cross-reference is resolved, which is fine for that
    purpose and avoids a parse dependency.

    The entry runs to the brace that closes the one it opened with, counted, so
    it does not matter whether that brace sits at the start of a line or is
    indented, nor whether the entry is written on one line. The earlier pattern
    required a ``}`` in column 0 and silently dropped everything else — a
    bibliography whose entries are indented parsed to nothing, and every
    citation against it would have been reported as not found.

    Returns an empty dict for malformed input — a bibliography that cannot be
    read yields no evidence, not a false accusation.
    """
    entries: Dict[str, Dict[str, str]] = {}
    position = 0
    for match in _ENTRY_START.finditer(bibtex):
        if match.start() < position:
            continue
        entry_type, key = match.group(1), match.group(3)
        body, position = _balanced(bibtex, match.start(2))
        entries[key] = {"type": entry_type.lower(), **_parse_fields(body)}
    return entries


def summarize(results: Iterable[ExistenceResult]) -> Dict[str, int]:
    """Count results by verdict, for a one-line report header."""
    counts = {VERDICT_VERIFIED: 0, VERDICT_NOT_FOUND: 0, VERDICT_UNKNOWN: 0}
    for r in results:
        counts[r.verdict] = counts.get(r.verdict, 0) + 1
    return counts
