import math
import re
from typing import Any

from .authors import split_authors


def collapse_whitespace(value) -> str:
    """One line, single spaces.

    Connectors hand over text as the API wrote it, and wrapped titles and
    abstracts carry the newline *and the indentation of the line below it*.
    Replacing only the newline left a run of spaces mid-sentence, which the
    scorer then failed to match: a two-word term straddling the wrap scored zero.
    """
    return " ".join(str(value or "").split())


_DOI_PREFIXES = (
    "https://dx.doi.org/",
    "http://dx.doi.org/",
    "https://doi.org/",
    "http://doi.org/",
    "dx.doi.org/",
    "doi:",
)


def normalize_doi(doi: str) -> str:
    """The bare DOI, lowercased — the identity every layer keys on.

    Stripping the prefixes in sequence, in the order they happened to be written,
    removed `dx.doi.org/` before the scheme and left `https://10.1234/abc`
    behind. That string feeds the identity index, the deduplication and the
    exported `.bib`, so one work written two ways became two papers.
    """
    if not doi:
        return ""
    value = str(doi).strip().lower()
    for prefix in _DOI_PREFIXES:
        if value.startswith(prefix):
            return value[len(prefix):].strip()
    return value


_ARXIV_URL_RE = re.compile(
    r"arxiv\.org/(?:abs|pdf)/(?P<id>[a-z\-]+(?:\.[a-z\-]+)?/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?",
    re.IGNORECASE,
)


def arxiv_id_from_url(url: str) -> str:
    """The bare arXiv id in a URL, without the version suffix, or an empty string.

    Both id spellings are matched, because arXiv minted ``cs/0701001`` before
    2007 and ``2107.10243`` after, and the connectors carry whichever the source
    handed them. The version suffix is dropped: ``2107.10243v2`` and
    ``2107.10243`` are the same work, and DataCite registers the DOI once.
    """
    if not url:
        return ""
    match = _ARXIV_URL_RE.search(str(url))
    if not match:
        return ""
    return match.group("id")


def arxiv_doi(arxiv_id: str) -> str:
    """The DataCite DOI arXiv mints for an id, or an empty string."""
    identifier = str(arxiv_id or "").strip()
    if not identifier:
        return ""
    return f"10.48550/arxiv.{identifier.lower()}"


def doi_from_url(url: str) -> str:
    """The DOI the URL itself implies, or an empty string.

    Only arXiv, today, because only arXiv writes an identifier into its URLs that
    maps onto a registered DOI. ``arxiv.org/abs/2310.01152v2`` is
    ``10.48550/arxiv.2310.01152``, computed exactly as
    ``enricher._citation_key`` computes it to ask a source for a citation count.

    A landing page implies nothing: CORE and the DOAJ records address a work
    without naming it, and an invented DOI would be worse than the empty column.
    """
    return arxiv_doi(arxiv_id_from_url(url))


def paper_order_key(paper, score_key: str = "Relevance_Score") -> tuple:
    """Total order over papers: score descending, then identity ascending.

    Sorting on the score alone left the relative order of equal scores to the
    order the papers happened to arrive in, and that order comes from concurrent
    mining, so it differs between runs of the same corpus: two runs with an
    identical ``Relevance_Score`` paper by paper produced 214 swapped rows, all
    of them inside a tie. The second element removes the dependence on arrival —
    the DOI where the paper has one, its title where it does not.

    ``normalize_doi`` is reused rather than a second identity rule invented, so
    that one work written as a bare DOI and as a URL lands in the same place.
    Papers carrying a DOI therefore sort before those without one inside a tie:
    arbitrary, but the same way round in every run, which is the whole point.

    The title is compared exactly as written, not slugged. ``title_slug`` drops
    every non-word character, so ``A-B`` and ``AB`` become one string — folding
    two distinct papers into one key, which puts them back on arrival order, the
    thing being removed. Lowercasing the DOI is the opposite case and is right:
    those two spellings are one work.

    A non-finite score counts as zero. ``nan`` compares false against everything,
    so its position would fall back on arrival order — the exact defect this key
    exists to remove, and one that would survive a tolerance check that only
    catches ``TypeError`` and ``ValueError``.
    """
    score = paper.get(score_key)
    try:
        score = float(score)
    except (TypeError, ValueError):
        score = 0.0
    if not math.isfinite(score):
        score = 0.0
    return (
        -score,
        normalize_doi(paper.get("DOI") or ""),
        str(paper.get("Title") or ""),
    )


def decode_abstract(inverted_index) -> str:
    """Rebuild an OpenAlex abstract from its inverted index.

    OpenAlex ships abstracts as ``{word: [positions]}`` rather than as text; the
    MCP tools read the same field, so the decoder lives here rather than on the
    connector they would otherwise have to instantiate to reach it.
    """
    if not inverted_index:
        return ""
    try:
        max_pos = max(max(pos) for pos in inverted_index.values())
        words = [""] * (max_pos + 1)
        for word, positions in inverted_index.items():
            for pos in positions:
                words[pos] = word
        return " ".join(words).strip()
    except Exception:
        return ""


_BIBTEX_ESCAPES = str.maketrans({
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "%": r"\%",
    "&": r"\&",
    "#": r"\#",
    "_": r"\_",
    "^": r"\textasciicircum{}",
})


def escape_bibtex(value: Any) -> str:
    """Escape what a LaTeX reader would act on instead of printing.

    A `}` in a title closes the field early, which is what the first three
    entries are for. The rest are the same failure one step later: `%` starts a
    comment, so `A 50% threshold` comments out the field's own closing brace and
    the record does not parse at all — the whole `.bib` is unreadable, not just
    that field. `&`, `#`, `_` and `^` are hard errors in text mode: a publisher
    name with an ampersand, a DOI fragment or an identifier with an underscore
    each stop the compile.

    `$` and `~` are deliberately left alone. `$` opens math mode, where the
    author put it on purpose, and `~` is a legal non-breaking space in text.

    The values come from third-party APIs, so the content is not ours to trust.
    """
    return str(value if value is not None else "").translate(_BIBTEX_ESCAPES)


def bibtex_authors(value: Any) -> str:
    """The author list in BibTeX's own separator, or an empty string.

    BibTeX joins names with a literal ``and``; the stored field joins them with
    ``;`` because a single name carries a comma. An entry with no authors is
    written without the field rather than with an empty one — ``author = {}``
    compiles to a reference with a blank where the name goes, which reads as a
    typesetting fault rather than as the missing data it is.
    """
    return " and ".join(split_authors(value))


_FORMULA_PREFIXES = ("=", "+", "-", "@")


def neutralise_formula(value: Any) -> Any:
    """Defuse a cell a spreadsheet would evaluate as a formula.

    A title or abstract starting with ``=``, ``+``, ``-`` or ``@`` runs as a
    formula when the file is opened in Excel or LibreOffice. These fields come
    from third-party APIs, so the content is not ours to trust.

    Leading whitespace does not make it safe: a spreadsheet drops it before it
    decides what the cell is, so ``"\\t=cmd|..."`` is the same formula as
    ``"=cmd|..."`` and ``startswith`` alone let it through. The check is made
    past the whitespace and the quote is added to the value as it arrived.
    """
    if isinstance(value, str) and value.lstrip().startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def one_line(value: Any) -> str:
    """Collapse a value onto one line: RIS is line-oriented, and a newline in a
    value ends the field and turns the rest into a tag the reader cannot place."""
    return " ".join(str(value if value is not None else "").split())
