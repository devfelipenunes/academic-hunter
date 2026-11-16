"""OpenAlex's address and identity, in one place.

The base URL, the domain the pacing is keyed by, the delay the source asks for
and the headers that identify a caller were spread across two modules that each
talked to this API — the pipeline's connector and the MCP discovery tools — and
each had its own copy. This is the copy.

It sits beside ``config.openalex_key`` rather than inside either caller for the
reason that function's own docstring gives: the credential is read by both, so
it lives where both can read it. The rest of the identity is the same kind of
fact.

The version is an argument and not an import of the package root, because this
module is imported while that root is still being built. Who we are and how we
say it live in ``transport``, which every source needs; what is specific to
OpenAlex is below.
"""

from typing import Any, Dict

from .config import openalex_key
from .transport import polite_email, user_agent

OPENALEX_BASE = "https://api.openalex.org"
OPENALEX_DOMAIN = "api.openalex.org"
OPENALEX_DEFAULT_DELAY = 1.5

def openalex_headers(settings: Dict[str, Any], version: str) -> Dict[str, str]:
    """What to send alongside an OpenAlex request: who we are, and the key if any.

    The key is optional — OpenAlex serves keyless callers — so it is absent
    rather than empty when there is none.
    """
    headers = {"User-Agent": user_agent(polite_email(settings), version)}
    key = openalex_key(settings)
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def openalex_params(settings: Dict[str, Any]) -> Dict[str, str]:
    """The query parameters that are about the caller rather than the query."""
    return {"mailto": polite_email(settings)}
