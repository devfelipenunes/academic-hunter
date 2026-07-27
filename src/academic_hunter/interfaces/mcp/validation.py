"""Input validation for MCP tool parameters."""

import re


def validate_doi(doi: str) -> str:
    """Validate and normalize a DOI. Raises ValueError if invalid."""
    if not doi or not doi.strip():
        raise ValueError("DOI is required.")
    doi = doi.strip()
    # Basic DOI format: 10.xxxx/xxxx
    if not re.match(r'^10\.\d{4,}/', doi):
        raise ValueError(f"Invalid DOI format: '{doi}'. Expected format: 10.xxxx/xxxx")
    return doi


def validate_query(query: str, field: str = "query") -> str:
    """Validate a search query string."""
    if not query or not query.strip():
        raise ValueError(f"{field} cannot be empty.")
    return query.strip()


def validate_limit(limit: int, default: int = 10, max_limit: int = 50) -> int:
    """Validate and clamp a limit parameter."""
    if limit is None:
        return default
    if not isinstance(limit, int) or limit < 1:
        return default
    return min(limit, max_limit)


def validate_topic(topic: str) -> str:
    """Validate a topic string."""
    if not topic or not topic.strip():
        raise ValueError("Topic cannot be empty.")
    return topic.strip()


def validate_email(email: str) -> str:
    """Basic email format validation."""
    if not email:
        return ""
    email = email.strip()
    if '@' not in email or '.' not in email.split('@')[-1]:
        raise ValueError(f"Invalid email format: '{email}'")
    return email


def validate_orcid(orcid_id: str) -> str:
    """Basic ORCID format validation (XXXX-XXXX-XXXX-XXXX)."""
    if not orcid_id or not orcid_id.strip():
        raise ValueError("ORCID iD is required.")
    orcid_id = orcid_id.strip()
    if not re.match(r'^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$', orcid_id):
        raise ValueError(f"Invalid ORCID format: '{orcid_id}'. Expected: XXXX-XXXX-XXXX-XXXX")
    return orcid_id
