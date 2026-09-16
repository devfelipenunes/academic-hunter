"""Numeric claim verification — layer 3.

Extracts the figures a manuscript asserts and confronts them with the values
actually present in the result files. This is the layer that catches a number
that no experiment produced.

It is deliberately a *closed-world* check against a declared set of sources, and
that shapes the verdicts:

- **MATCHED** — the value appears in the results.
- **CLOSE** — a near value appears (rounding, different precision).
- **UNSOURCED** — no value anywhere near it. This is a prompt to look, not a
  conviction: a manuscript legitimately quotes figures from cited literature,
  which is not in the result files. The report says which files were searched so
  the reader can tell the two cases apart.

The distinction mirrors ``citations.verify_existence``: "we found no source for
this" is reported as its own verdict, never as "this is wrong".
"""

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Set

STATUS_MATCHED = "MATCHED"
STATUS_CLOSE = "CLOSE"
STATUS_UNSOURCED = "UNSOURCED"

# A percentage: "93.0%", "92.7 %"
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
# A correlation, in either markdown math or plain text: "ρ = 0.968", "$\\rho = -0.084$"
_CORRELATION = re.compile(r"(?:ρ|\\rho)\s*=\s*(-?\d+(?:\.\d+)?)")
# A p-value in the rendering `format_statistical_claim` produces:
# "p = 1.57 × 10⁻⁷³". The superscript digits are translated, not parsed.
_PVALUE_SCIENTIFIC = re.compile(
    r"p\s*[=<>]\s*(\d+(?:\.\d+)?)\s*[×x]\s*10\s*\^?\s*([⁻⁺-]?[⁰¹²³⁴⁵⁶⁷⁸⁹0-9]+)"
)
# A p-value: "p = 1.57e-73", "p < 0.0001", "p = 0.012"
_PVALUE = re.compile(r"p\s*[=<>]\s*(\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")
# A count of things: "1,538 papers", "586 papers", "304 papers"
_COUNT = re.compile(r"(\d[\d,]*)\s+(?:papers|titles|records|studies|documents)\b")
# A bare decimal in prose — the weakest signal, only used when nothing else
# matched. The sign is kept: dropping it made `-0.5` match a stored `+0.5`, and a
# false match endorses a claim while a false miss only asks someone to look.
_BARE = re.compile(r"(?<![\w.])(-?\d+\.\d+)")

# Numbers that are structural references, not findings: "§3.13", "Table 2.1",
# "Section 3.2", "phase 0.5". Reporting these as unsourced figures buries the
# real findings in noise — the first run produced 131 bogus "close" matches
# from section numbers alone.
_STRUCTURAL_REF = re.compile(
    r"(?:§|\\S|Section|Sect\.|Table|Figure|Fig\.|Algorithm|Chapter|phase|Phase)"
    r"\s*(\d+(?:\.\d+)*)",
    re.IGNORECASE,
)
# Numbered markdown headings: "## 2.1 Bi-encoder Background". Without this the
# heading numbers are extracted as findings — they have no § prefix to filter on.
_HEADING = re.compile(r"^#{1,6}\s+\d+(?:\.\d+)+", re.MULTILINE)
# Markdown table separator rows: "| ----: | ----: |"
_TABLE_RULE = re.compile(r"^\s*\|[\s:|-]+\|\s*$", re.MULTILINE)

_SENTENCE = re.compile(r"[^.!?]*[.!?]")


@dataclass
class NumericClaim:
    """A figure asserted in the text, with where it was asserted."""

    value: float
    raw: str
    kind: str
    context: str
    offset: int


@dataclass
class NumberResult:
    """Outcome for one asserted figure."""

    claim: NumericClaim
    status: str = STATUS_UNSOURCED
    matched_value: Optional[float] = None
    evidence: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "raw": self.claim.raw,
            "value": self.claim.value,
            "kind": self.claim.kind,
            "status": self.status,
            "matched_value": self.matched_value,
        }


def _sentence_around(text: str, position: int) -> str:
    start = 0
    for sentence in _SENTENCE.finditer(text[:position]):
        start = sentence.end()
    end_match = _SENTENCE.search(text, position)
    end = end_match.end() if end_match else len(text)
    return " ".join(text[start:end].split())


_SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺", "0123456789-+")


def _as_float(raw: str) -> float:
    return float(raw.replace(",", ""))


def _plain(match: "re.Match") -> float:
    return _as_float(match.group(1))


def _scientific(match: "re.Match") -> float:
    exponent = int(match.group(2).translate(_SUPERSCRIPT))
    return float(match.group(1)) * 10**exponent


def extract_claims(text: str) -> List[NumericClaim]:
    """Find every checkable figure in a text.

    A given position is claimed once, by the most specific pattern that matches
    it — a percentage is not also reported as a bare decimal. Structural
    references (``§3.13``, ``Table 2.1``) are excluded: they are pointers, not
    findings, and including them buries the real figures in noise.
    """
    claims: List[NumericClaim] = []
    taken: List[tuple[int, int]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(start < e and end > s for s, e in taken)

    # Reserve the spans of structural references first, so no later pattern can
    # claim a section number as a finding.
    for pattern in (_STRUCTURAL_REF, _HEADING, _TABLE_RULE):
        for match in pattern.finditer(text):
            taken.append(match.span())

    # Order matters: the first pattern to claim a span wins, so the superscript
    # form is tried before the plain one, which would otherwise take "p = 1.57"
    # and leave the exponent behind.
    patterns = [
        (_PERCENT, "percent", _plain),
        (_CORRELATION, "correlation", _plain),
        (_PVALUE_SCIENTIFIC, "pvalue", _scientific),
        (_PVALUE, "pvalue", _plain),
        (_COUNT, "count", _plain),
        (_BARE, "decimal", _plain),
    ]

    for pattern, kind, value_of in patterns:
        for match in pattern.finditer(text):
            start, end = match.span()
            if overlaps(start, end):
                continue
            taken.append((start, end))
            claims.append(
                NumericClaim(
                    value=value_of(match),
                    raw=match.group(0).strip(),
                    kind=kind,
                    context=_sentence_around(text, start),
                    offset=start,
                )
            )

    claims.sort(key=lambda c: c.offset)
    return claims


def iter_numbers(node: Any) -> Iterator[float]:
    """Yield every number inside a nested JSON structure.

    Booleans are skipped deliberately: ``True`` is an ``int`` in Python and would
    otherwise pollute the index with 1.0.
    """
    if isinstance(node, bool):
        return
    if isinstance(node, (int, float)):
        yield float(node)
    elif isinstance(node, dict):
        for value in node.values():
            yield from iter_numbers(value)
    elif isinstance(node, list):
        for value in node:
            yield from iter_numbers(value)


def index_results(results_dir: Path) -> Set[float]:
    """Collect every number appearing in the result files under a directory.

    Unreadable or malformed files are skipped rather than failing the run: a
    partial index narrows what can be confirmed, but must not fabricate an
    absence.
    """
    known: Set[float] = set()
    if not results_dir.is_dir():
        return known
    for path in sorted(results_dir.rglob("*.json")):
        try:
            known.update(iter_numbers(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
    return known


def _decimals(value: float) -> int:
    """How many decimal places the value was written with.

    This drives the comparison: a figure written as 92.7 must be checked at one
    decimal place, not against every nearby float.
    """
    text = repr(float(value))
    if "." not in text:
        return 0
    return len(text.split(".")[1].rstrip("0"))


def verify_numbers(
    claims: Iterable[NumericClaim],
    known: Set[float],
    close_tolerance: float = 0.001,
) -> List[NumberResult]:
    """Confront asserted figures with the values found in the result files.

    Comparison is by **precision, not tolerance** — and that is the lesson from
    running this against a real manuscript. An earlier version accepted any
    indexed value within 1% relative. Measured against the project's own result
    files, 237 of 338 values sit within 1% of some other value, so the check
    accepted a fabricated 87.3% (the files contain 0.871) and reported zero
    unsourced figures out of 191 claims. A verifier that confirms everything
    verifies nothing.

    Instead, a claim is matched only when an indexed value agrees with it *at
    the precision the claim was written to*: 92.7% matches 0.927, and 87.3% does
    not match 0.871. A near miss within ``close_tolerance`` is reported as CLOSE
    — flagged, but not counted as confirmation — and everything else is
    UNSOURCED.
    """
    results: List[NumberResult] = []

    for claim in claims:
        result = NumberResult(claim=claim)
        if not known:
            result.status = STATUS_UNSOURCED
            result.evidence = "no result files were indexed"
            results.append(result)
            continue

        decimals = _decimals(claim.value)
        target = round(claim.value, decimals)

        # A percentage may be stored either way: 92.7 in the text, 0.927 in JSON.
        scales = (1.0, 100.0) if claim.kind == "percent" else (1.0,)

        exact: Optional[float] = None
        nearest: Optional[float] = None
        nearest_delta = math.inf

        for value in known:
            for scale in scales:
                scaled = value * scale
                if round(scaled, decimals) == target:
                    exact = value
                    break
                delta = abs(scaled - claim.value)
                if delta < nearest_delta:
                    nearest_delta, nearest = delta, value
            if exact is not None:
                break

        if exact is not None:
            result.status = STATUS_MATCHED
            result.matched_value = exact
            result.evidence = f"result files contain {exact}"
        elif nearest is not None and nearest_delta <= close_tolerance * max(abs(claim.value), 1.0):
            result.status = STATUS_CLOSE
            result.matched_value = nearest
            result.evidence = (
                f"nearest value is {nearest} — differs by {nearest_delta:g}; "
                "treat as unconfirmed"
            )
        else:
            result.status = STATUS_UNSOURCED
            result.evidence = "no result file contains a value at this precision"

        results.append(result)

    return results


def summarize_numbers(results: Iterable[NumberResult]) -> Dict[str, int]:
    """Count number-verification results by status."""
    counts = {STATUS_MATCHED: 0, STATUS_CLOSE: 0, STATUS_UNSOURCED: 0}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    return counts
