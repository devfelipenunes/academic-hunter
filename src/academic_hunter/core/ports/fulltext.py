"""Full-text port — obtaining a paper's body and turning it into text.

``Protocol`` rather than ABC, for the same reason as
:mod:`academic_hunter.core.ports.connector`: the adapters wrap third-party code
(HTTP for Unpaywall, ``pypdf`` for extraction), and forcing them to inherit a
domain ABC would drag transport concerns into ``core``.
"""

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable


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
    """This document could not be fetched; the run continues without it."""


class FullTextConfigError(FullTextError):
    """The configuration is unusable, so every attempt would fail the same way.

    Aborts the step. Collapsing this into the transient case is how a run ends up
    making dozens of doomed HTTP calls with a malformed e-mail before giving up.
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
