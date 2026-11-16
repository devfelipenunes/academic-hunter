"""Full-text outcomes — what an attempt to obtain a paper's body can return.

The exception hierarchy is the point of this module: "no open-access copy
exists" and "the download broke" need different fixes and only one is worth
retrying, so a run that reports a single failure count is reporting nothing it
can act on.

The adapters (HTTP for Unpaywall, ``pypdf`` for extraction) wrap third-party
code and implement the shape by duck typing rather than inheriting from a base
declared here, which would drag transport concerns into ``core``.
"""

from dataclasses import dataclass, field
from typing import List


class FullTextError(Exception):
    """Base for the three outcomes a full-text attempt can have."""


class NoOpenAccessVersion(FullTextError):  # noqa: N818
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

    BLOCKED = "blocked"
    NOT_FOUND = "not_found"
    NO_PDF = "no_pdf"
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
    has_text_layer: bool = True
    source: str = ""
    page_spans: List["PageSpan"] = field(default_factory=list)


@dataclass(frozen=True)
class PageSpan:
    """Character offsets for one source page in the extracted document text."""

    start: int
    end: int
    page: int
