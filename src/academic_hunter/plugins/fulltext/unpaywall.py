"""Unpaywall client — locating and fetching open-access copies of a DOI.

Logic extracted from the MCP tool, which keeps its ``ctx`` messages and delegates
here — the same shape as ``plugins/exporters/obsidian.py``. The pipeline needs
this without importing the interface layer.
"""

import logging
from typing import Any, Dict

import requests

from ...core.ports.fulltext import (
    FullTextConfigError,
    FullTextTransientError,
    NoOpenAccessVersion,
    OpenAccessLocation,
)

logger = logging.getLogger("academic_hunter.fulltext.unpaywall")

UNPAYWALL_API = "https://api.unpaywall.org/v2"

DEFAULT_TIMEOUT = 10

#: A PDF larger than this is aborted mid-stream rather than held in memory.
MAX_PDF_BYTES = 40_000_000

_CHUNK = 64 * 1024


def fetch_record(doi: str, email: str, timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """The raw Unpaywall record for a DOI.

    Raises:
        FullTextConfigError: Unpaywall refused the e-mail (HTTP 422). Every
            subsequent call would fail the same way, so the caller should stop.
        NoOpenAccessVersion: Unpaywall does not know this DOI.
        FullTextTransientError: the request itself failed.
    """
    try:
        response = requests.get(
            f"{UNPAYWALL_API}/{doi}", params={"email": email}, timeout=timeout
        )
    except requests.RequestException as e:
        raise FullTextTransientError(f"Unpaywall request failed: {e}") from e

    if response.status_code == 422:
        raise FullTextConfigError(
            "Unpaywall rejected the configured e-mail. Set settings.unpaywall_email "
            "to a valid address."
        )
    if response.status_code == 404:
        raise NoOpenAccessVersion(doi)
    if response.status_code != 200:
        raise FullTextTransientError(f"Unpaywall returned HTTP {response.status_code}")

    try:
        return response.json()
    except ValueError as e:
        raise FullTextTransientError(f"Unpaywall returned invalid JSON: {e}") from e


class UnpaywallSource:
    """A :class:`FullTextSourcePort` over the Unpaywall API."""

    def __init__(self, email: str, timeout: int = DEFAULT_TIMEOUT) -> None:
        if not email or "@" not in email:
            # Caught at construction so a run cannot make hundreds of doomed
            # requests before anyone notices the address is unusable.
            raise FullTextConfigError(
                f"Unpaywall needs a valid contact e-mail, got {email!r}. "
                "Set settings.unpaywall_email."
            )
        self.email = email
        self.timeout = timeout

    def locate(self, doi: str) -> OpenAccessLocation:
        """Where the open-access copy lives.

        Raises:
            NoOpenAccessVersion: there is no OA copy, which is the common case.
            FullTextConfigError: the contact e-mail was refused.
            FullTextTransientError: the lookup failed.
        """
        record = fetch_record(doi, self.email, self.timeout)
        if not record.get("is_oa"):
            raise NoOpenAccessVersion(doi)

        best = record.get("best_oa_location") or {}
        url = best.get("url_for_pdf") or best.get("url")
        if not url:
            raise NoOpenAccessVersion(doi)

        return OpenAccessLocation(
            url=url,
            host=str(best.get("host_type") or ""),
            version=str(best.get("version") or ""),
            license=str(best.get("license") or ""),
        )

    def download(
        self, location: OpenAccessLocation, max_bytes: int = MAX_PDF_BYTES
    ) -> bytes:
        """The PDF bytes, capped at ``max_bytes``.

        The cap is enforced twice: once against the declared Content-Length, and
        again while streaming, because a header can be absent or lie.

        Raises:
            FullTextTransientError: the download failed, was too large, or was
                not a PDF — a publisher landing page returns HTML with HTTP 200.
        """
        try:
            response = requests.get(location.url, timeout=self.timeout, stream=True)
            response.raise_for_status()
        except requests.RequestException as e:
            raise FullTextTransientError(f"Download failed for {location.url}: {e}") from e

        declared = response.headers.get("Content-Length", "")
        if declared.isdigit() and int(declared) > max_bytes:
            response.close()
            raise FullTextTransientError(
                f"{declared} bytes exceeds the {max_bytes}-byte cap"
            )

        payload = bytearray()
        try:
            for block in response.iter_content(_CHUNK):
                payload.extend(block)
                if len(payload) > max_bytes:
                    raise FullTextTransientError(
                        f"Body exceeded the {max_bytes}-byte cap while streaming"
                    )
        finally:
            response.close()

        if not payload.startswith(b"%PDF-"):
            raise FullTextTransientError(
                f"{location.url} did not return a PDF (a landing page, most likely)"
            )
        return bytes(payload)
