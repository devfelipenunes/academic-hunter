"""Authorship — the one field a citable reference cannot do without.

Every connector is handed authors by its API and not one of them read the field,
so the exported ``.bib`` of a full run carried ``title``, ``journal``, ``year``,
``doi``, ``abstract`` and **no ``author``** on any of its 310 entries. A wrong
year is a wrong reference; a missing author is not a reference at all.

The value is one string joined by ``"; "`` rather than a list, for the same
reason ``Source`` and ``Citations_Source`` already are: ``FIELD_SCHEMA`` is
scalar, and the CSV writes the field as it stands. The separator cannot be
``", "`` — a name written ``"Family, Given"`` carries one.

Two spellings of a name reach this module, and neither is converted into the
other. Crossref publishes ``family`` and ``given`` separately, so it is written
in the comma form BibTeX also uses. OpenAlex, arXiv and Semantic Scholar publish
only a display name, and splitting that back into halves would guess at where
the surname ends — wrong for ``van der Berg``, wrong for a mononym. Splitting is
therefore done only where the API already did it.
"""

from typing import Any, Iterable, List

AUTHOR_SEPARATOR = "; "


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def format_name(family: Any, given: Any) -> str:
    """``"Family, Given"`` when both halves are known, else whichever exists."""
    family_str = _clean(family)
    given_str = _clean(given)
    if family_str and given_str:
        return f"{family_str}, {given_str}"
    return family_str or given_str


def join_authors(names: Iterable[Any]) -> str:
    """Deduplicate case-insensitively, keeping the first spelling and the order.

    Order is the author order, which a citation reproduces, so it cannot go
    through a ``set`` the way ``strategy_set_join`` does for source names.
    """
    seen = set()
    ordered: List[str] = []
    for name in names:
        cleaned = _clean(name)
        if not cleaned or cleaned.lower() in seen:
            continue
        seen.add(cleaned.lower())
        ordered.append(cleaned)
    return AUTHOR_SEPARATOR.join(ordered)


def split_authors(value: Any) -> List[str]:
    if isinstance(value, (list, tuple, set)):
        return [_clean(item) for item in value if _clean(item)]
    return [part.strip() for part in str(value or "").split(AUTHOR_SEPARATOR) if part.strip()]


def normalize_authors(value: Any) -> str:
    return join_authors(split_authors(value))


def crossref_authors(items: Any) -> str:
    """Crossref ``author``: structured halves, or a single ``name`` for a body."""
    if not isinstance(items, list):
        return ""
    names = []
    for item in items:
        if not isinstance(item, dict):
            continue
        names.append(format_name(item.get("family"), item.get("given")) or _clean(item.get("name")))
    return join_authors(names)


def openalex_authors(authorships: Any) -> str:
    """OpenAlex ``authorships``: a display name per author and no halves."""
    if not isinstance(authorships, list):
        return ""
    names = []
    for entry in authorships:
        if isinstance(entry, dict):
            author = entry.get("author")
            if isinstance(author, dict):
                names.append(author.get("display_name"))
    return join_authors(names)


def listed_authors(items: Any) -> str:
    """A ``[{"name": ...}, ...]`` list, the shape arXiv and Semantic Scholar use."""
    if not isinstance(items, list):
        return ""
    names = [item.get("name") if isinstance(item, dict) else item for item in items]
    return join_authors(names)
