"""The author's writing conventions, as functions.

These are not cosmetic preferences — they are what separates text that reads as
the author's from generic LLM prose. They were extracted from the author's three
manuscripts, which are not in this repository, and from the citation keys in
their bibliographies.

Keeping them here (rather than in a prompt) means the deterministic parts of an
article are produced by code that can be tested, and the agent's freedom is
confined to the prose itself.
"""

import hashlib
import re
from typing import Any, Iterable, List, Mapping, Optional, Sequence

from ..models.utils import normalize_doi

_MULTI_SPACE = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

_STOPWORDS = {
    "a", "an", "the", "on", "of", "in", "for", "and", "or", "to", "with",
    "toward", "towards", "from", "at", "by", "is", "are",
}


def format_citation(keys: Iterable[str]) -> str:
    """Render pandoc-style citation keys.

    Single: ``[@echo2024]``. Multiple: ``[@queenbee2026; @hybridagentic2026]``.

    Keys are emitted in the order given — the author orders them deliberately
    (usually the most relevant first), so this does not sort.
    """
    cleaned = [k.strip().strip("[]").lstrip("@").strip() for k in keys]
    cleaned = [k for k in cleaned if k]
    if not cleaned:
        raise ValueError("format_citation requires at least one key")
    return "[@" + "; @".join(cleaned) + "]"


def format_bibtex_key(title: str, year: int | str, author: Optional[str] = None) -> str:
    """Build a citation key in the author's convention.

    The dominant pattern in the existing ``.bib`` files is
    *stem + year*, lowercase, no underscores: ``echo2024``, ``asreview2020``,
    ``mcp2024``. The stem is the author's surname when given, otherwise the
    first meaningful word of the title.

    An acronym-looking first token of a title (``MCP``, ``SGPT``, ``SIF``) is
    kept whole, matching keys like ``mcp2024`` and ``sgpt2022``.

    An author is read in either order. Taking the last word assumed
    "Given Family", so the bibliography style that writes "Family, Given" —
    which is the one this project's own sources use — produced the given name.
    """
    if author:
        stem = author.split(",")[0] if "," in author else author.split()[-1]
    else:
        words = [w for w in _MULTI_SPACE.split(title.strip()) if w]
        words = [w for w in words if _NON_ALNUM.sub("", w.lower()) not in _STOPWORDS]
        stem = words[0] if words else (title or "ref")

    stem = _NON_ALNUM.sub("", stem.lower())
    if not stem:
        stem = "ref"
    return f"{stem}{year}"


def _field(paper: Mapping[str, Any], *names: str) -> str:
    """The first of ``names`` the paper carries a non-empty value under."""
    for name in names:
        value = paper.get(name)
        if value not in (None, ""):
            return str(value)
    return ""


def _doi_suffix(doi: str) -> str:
    """A short, stable tag for one DOI.

    A digest rather than the readable tail of the DOI: `10.1/echo-a` and
    `10.2/echo-a` share a tail, and two papers sharing a key is the defect this
    suffix exists to remove. Eight hex characters keep it bounded whatever the
    DOI's length and punctuation, and the same DOI always yields the same tag,
    which is what lets two independent callers agree without coordinating.
    """
    return hashlib.sha256(normalize_doi(doi).encode("utf-8")).hexdigest()[:8]


def paper_citation_key(paper: Mapping[str, Any]) -> str:
    """The citation key of one paper, derived from that paper alone.

    Both sides of the seam go through here: the tool that tells the agent which
    key to cite, and the exporter that writes the bibliography. Deriving the key
    from the paper — rather than from its position in whatever collection each
    side happens to hold — is what lets the two agree without coordinating. An
    allocator cannot: it disambiguates by position, and the tool sees a
    similarity-ranked subset while the exporter sees the whole run in another
    order, so a colliding pair came out as `echo2024` from one side and
    `echo2024-2` from the other — a citation that resolves, to the wrong paper.

    A paper with a DOI carries its tag, so `format_bibtex_key`'s collisions
    (same stem, same year, different works) stop sharing a key. A paper without
    one keeps the bare `stem+year` this project's bibliographies already use.

    The corpus rows the vector store returns name their fields in lower case
    (`title`, `doi`, `year`); the export rows use the model's field names
    (`Title`, `DOI`, `Year`). Accepting both is what makes one function usable
    by both.
    """
    title = _field(paper, "Title", "title")
    year = _field(paper, "Year", "year")
    key = format_bibtex_key(title, year)

    doi = _field(paper, "DOI", "doi")
    return f"{key}-{_doi_suffix(doi)}" if doi else key


def format_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[object]],
    caption: Optional[str] = None,
    table_number: Optional[int] = None,
    highlight_row: Optional[int] = None,
    right_align: Optional[Sequence[int]] = None,
    footnote: Optional[str] = None,
) -> str:
    """Render a markdown pipe table in the author's style.

    Conventions applied:
    - the caption sits **above** the table as a bold line: ``**Table 2: title**``
    - numeric columns are right-aligned (``----:``)
    - one row may be bolded — the winner in a comparison
    - an optional footnote marker is appended and explained below the table

    Args:
        headers: column headings.
        rows: row values; any object is stringified.
        caption: table title. Rendered only when given.
        table_number: included in the caption as ``Table N:``.
        highlight_row: index into ``rows`` to bold entirely.
        right_align: column indices to right-align. Defaults to all columns
            except the first, which is the usual shape in these manuscripts.
        footnote: explanatory text rendered under the table, prefixed with a
            superscript marker matching the one appended to the caption.
    """
    if not headers:
        raise ValueError("format_table requires at least one header")
    width = len(headers)
    for i, row in enumerate(rows):
        if len(row) != width:
            raise ValueError(
                f"Row {i} has {len(row)} cells but there are {width} headers"
            )

    if right_align is None:
        right_align = list(range(1, width))
    align_set = set(right_align)

    out: List[str] = []
    if caption:
        number = f"Table {table_number}: " if table_number is not None else ""
        marker = "¹" if footnote else ""
        out.append(f"**{number}{caption}**{marker}")
        out.append("")

    def render_row(cells: Sequence[object], bold: bool) -> str:
        rendered = []
        for c in cells:
            text = str(c)
            rendered.append(f"**{text}**" if bold and text else text)
        return "| " + " | ".join(rendered) + " |"

    out.append(render_row(headers, False))
    out.append(
        "| " + " | ".join("----:" if i in align_set else "----" for i in range(width)) + " |"
    )
    for i, row in enumerate(rows):
        out.append(render_row(row, bold=(highlight_row == i)))

    if footnote:
        out.append("")
        out.append(f"¹ {footnote}")

    return "\n".join(out)


def format_equation(latex: str, where: Optional[str] = None) -> str:
    """Render an equation in block form, with the author's 'where…' clause.

    Equations are always ``$$…$$`` on their own lines — never an isolated inline
    ``$…$`` on a line by itself. A symbol glossary is expected beneath: the
    manuscripts consistently follow a formula with a paragraph explaining each
    symbol.
    """
    body = f"$$\n{latex.strip()}\n$$"
    if where:
        clause = where.strip()
        if not clause.lower().startswith("where"):
            clause = f"where {clause}"
        body = f"{body}\n\n{clause}"
    return body


def format_statistical_claim(
    statistic: str,
    dof: Optional[int] = None,
    p_value: Optional[float] = None,
    ci: Optional[tuple[float, float]] = None,
    effect_size: Optional[tuple[str, float]] = None,
) -> str:
    """Render a significance claim with the components the author always reports.

    Example output: ``t(499) = 21.60, p = 1.57 × 10⁻⁷³, Cohen's d = 0.35``.

    p-values are rendered in scientific notation with the exponent as a
    superscript, matching the manuscripts.
    """
    parts: List[str] = []
    parts.append(f"{statistic}({dof})" if dof is not None else statistic)

    if p_value is not None:
        mantissa, exponent = f"{p_value:.2e}".split("e")
        exp = int(exponent)
        superscript = str(exp).replace("-", "⁻").translate(
            str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
        )
        parts.append(f"p = {mantissa} × 10{superscript}")
    if ci is not None:
        parts.append(f"95% CI [{ci[0]:.3f}, {ci[1]:.3f}]")
    if effect_size is not None:
        name, value = effect_size
        parts.append(f"{name} = {value}")

    return ", ".join(parts)
