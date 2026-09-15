def collapse_whitespace(value) -> str:
    """One line, single spaces.

    Connectors hand over text as the API wrote it, and wrapped titles and
    abstracts carry the newline *and the indentation of the line below it*.
    Replacing only the newline left a run of spaces mid-sentence, which the
    scorer then failed to match: a two-word term straddling the wrap scored zero.
    """
    return " ".join(str(value or "").split())


def normalize_doi(doi: str) -> str:
    if not doi:
        return ""
    return str(doi).strip().lower().replace('https://doi.org/', '').replace('http://doi.org/', '').replace('dx.doi.org/', '').replace('http://dx.doi.org/', '')
