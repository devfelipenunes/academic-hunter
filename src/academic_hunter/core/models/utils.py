def collapse_whitespace(value) -> str:
    """One line, single spaces.

    Connectors hand over text as the API wrote it, and wrapped titles and
    abstracts carry the newline *and the indentation of the line below it*.
    Replacing only the newline left a run of spaces mid-sentence, which the
    scorer then failed to match: a two-word term straddling the wrap scored zero.
    """
    return " ".join(str(value or "").split())


#: Longest first: the scheme and the host are one prefix, not two removals.
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
