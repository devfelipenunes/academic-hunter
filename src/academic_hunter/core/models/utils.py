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


ABSTRACT_PLACEHOLDERS = frozenset({
    "abstract",
    "no abstract",
    "sem abstract",
    "sem resumo",
    "abstract not available",
    "abstract unavailable",
    "resumo não disponível",
})

_PLACEHOLDER_EDGES = " .:;-–—"


def strip_abstract_placeholder(value: Any) -> str:
    """A note where an abstract should be, returned as no abstract at all.

    A source can fill the field with a note that there is nothing to fill it
    with rather than leaving it empty, and such a note survives every emptiness
    check in the pipeline while still reading as content. It is not what this
    run had — the two papers of run 20261008_091529 without an abstract carry an
    empty cell — so this is a guard against the shape and not a repair of the
    corpus that prompted it. What the corpus did need is ``abstract_summary``
    disclosing the empties and the scorer withholding the title multiplier on
    them.

    Matched exactly, past the collapsed whitespace and any edge punctuation, and
    never as a substring. A real abstract that happens to contain the word
    "abstract" is a real abstract, and truncating it would be the worse of the
    two faults. The comparison is on the whole value, so it cannot do that.
    """
    text = collapse_whitespace(value)
    if text.strip(_PLACEHOLDER_EDGES).lower() in ABSTRACT_PLACEHOLDERS:
        return ""
    return text


_TITLE_LABEL = re.compile(r"^\s*title\s*[:.\-–—]\s*", re.IGNORECASE)


def strip_title_label(value: Any) -> str:
    """A title that arrived with its own field name glued to the front.

    One source handed back ``"Title: Distributed Ledger Technology…"`` while
    another handed the same paper bare. The label survives into the identity --
    ``title_slug`` folds the first to ``titledistributedledger…`` and the second
    to ``distributedledger…`` -- so the deduplication never matches them and the
    run keeps both copies. Measured: one such pair in a 78-paper run. The DOI
    pass does not save it either, because the labelled copy carried a DOI and the
    bare one carried none.

    Only a label standing alone at the very front is removed, and only when a
    separator follows it. A title that merely contains the word is a title, and
    truncating it would be the worse of the two faults -- the same reasoning as
    :func:`strip_abstract_placeholder`, one field over.

    Collapsing the whitespace is part of this, so it replaces
    ``collapse_whitespace`` at the call sites rather than sitting beside it.
    """
    return _TITLE_LABEL.sub("", collapse_whitespace(value), count=1)


def abstract_text(paper) -> str:
    """A paper's abstract under either spelling.

    Papers carry the schema's field name; the score-distribution sidecar writes
    its columns in lower case. Both are read so one summary describes the
    collection and the artifact written from it, and the two cannot drift.
    """
    if "Abstract" in paper:
        return paper.get("Abstract") or ""
    return paper.get("abstract") or ""


def has_abstract(paper) -> bool:
    """Whether a paper carries an abstract the scorer and the gate can read."""
    return bool(strip_abstract_placeholder(abstract_text(paper)).strip())


def abstract_summary(papers) -> dict:
    """How much of a corpus is readable, and which papers are not.

    A paper with no abstract is not screened the way the rest are: the anchor
    gate and its context rules run over title and abstract concatenated, so with
    the abstract empty they run over the title alone, and the keyword score is
    the title's terms with nothing to balance them. The count belongs in the
    report for the same reason the citation coverage does — a corpus that is
    partly unscreenable and does not say so reads as a corpus that was screened.
    """
    summary = {
        "papers": 0,
        "with_abstract": 0,
        "without_abstract": 0,
        "without_abstract_titles": [],
    }
    for paper in papers:
        summary["papers"] += 1
        if has_abstract(paper):
            summary["with_abstract"] += 1
            continue
        summary["without_abstract"] += 1
        summary["without_abstract_titles"].append(str(paper.get("Title") or paper.get("title") or ""))
    return summary


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
