"""Full-text port — obtaining a paper's body and turning it into text.

``Protocol`` rather than ABC, for the same reason as
:mod:`academic_hunter.core.ports.connector`: the adapters wrap third-party code
(HTTP for Unpaywall, ``pypdf`` for extraction), and forcing them to inherit a
domain ABC would drag transport concerns into ``core``.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class FullTextError(Exception):
    """Base for the three outcomes a full-text attempt can have."""


class NoOpenAccessVersion(FullTextError):
    """No open-access copy of this DOI exists.

    Not a failure — it is the common case, and the reason the port distinguishes
    outcomes at all: a run has to report how many full texts it could not obtain
    and why, and "there is no OA copy" is a different finding from "the download
    broke".
    """


class FullTextTransientError(FullTextError):
    """This document could not be fetched; the run continues without it.

    ``kind`` says which of the several causes it was, because they need
    different fixes and only one of them is worth retrying. The message already
    carried the cause, as free text truncated to 300 characters; a field makes
    it countable without reading prose, and survives the truncation.
    """

    #: The server refused this client (401/403/406) — a retry gets the same answer.
    BLOCKED = "blocked"
    #: The DOI is gone (404).
    NOT_FOUND = "not_found"
    #: A 200 that was not a PDF — a landing page, so no file was ever there.
    NO_PDF = "no_pdf"
    #: Network trouble or a 5xx: the only kind a second pass can plausibly recover.
    TRANSIENT = "transient"

    def __init__(self, message: str, kind: str = TRANSIENT) -> None:
        super().__init__(message)
        self.kind = kind

    @classmethod
    def for_status(cls, status: int, message: str) -> "FullTextTransientError":
        """Classify an HTTP failure by the status that caused it."""
        if status in (401, 403, 406):
            return cls(message, cls.BLOCKED)
        if status == 404:
            return cls(message, cls.NOT_FOUND)
        return cls(message, cls.TRANSIENT)


class FullTextConfigError(FullTextError):
    """A source could not be used because of its configuration.

    Distinct from the transient case so the caller can say "fix the config"
    rather than "the network was down". It does not abort the step: a chain
    raises it only after every source failed for one DOI, and the sources do not
    share configuration — an e-mail one repository rejects leaves the others
    working. The time budget, not this exception, bounds a run going nowhere.
    """


@dataclass
class OpenAccessLocation:
    """Where an open-access copy lives."""

    url: str
    host: str = ""
    version: str = ""
    license: str = ""


@dataclass
class ExtractedDocument:
    """Text pulled from a PDF, with what the chunker needs to section it."""

    text: str
    page_count: int = 0
    #: False when the PDF carries no text layer (a scan). No OCR is attempted.
    has_text_layer: bool = True
    #: Which leg of the chain delivered it — a coverage report needs to say which
    #: source could actually produce the text, not just that there was one.
    source: str = ""


@runtime_checkable
class FullTextSourcePort(Protocol):
    """Locating and fetching an open-access copy."""

    def locate(self, doi: str) -> OpenAccessLocation:
        """Return where the OA copy lives.

        Raises:
            NoOpenAccessVersion: there is none.
            FullTextTransientError: the lookup itself failed.
            FullTextConfigError: the request could never succeed as configured.
        """
        ...

    def download(self, location: OpenAccessLocation, max_bytes: int = 40_000_000) -> bytes:
        """Return the PDF bytes, never more than ``max_bytes``.

        The cap is enforced while streaming: a Content-Length that lies, or is
        absent, must not turn into an unbounded read into memory.

        Raises:
            FullTextTransientError: the download failed, or was not a PDF.
        """
        ...


@runtime_checkable
class TextExtractorPort(Protocol):
    """Turning PDF bytes into text."""

    def extract(self, pdf_bytes: bytes) -> ExtractedDocument:
        """Return the document's text.

        Raises:
            FullTextTransientError: the file is corrupt or could not be parsed.
        """
        ...
