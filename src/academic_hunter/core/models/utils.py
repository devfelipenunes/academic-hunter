def normalize_doi(doi: str) -> str:
    if not doi:
        return ""
    return str(doi).strip().lower().replace('https://doi.org/', '').replace('http://doi.org/', '').replace('dx.doi.org/', '').replace('http://dx.doi.org/', '')
