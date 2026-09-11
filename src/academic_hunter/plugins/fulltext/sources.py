"""Composing the full-text adapters into something a step can call.

The step wants one thing — a DOI in, a document out — while the sources differ
in transport (HTTP vs API), format (PDF vs JATS XML) and coverage (Unpaywall
knows where copies live, Europe PMC actually serves some of them). This module
is the seam between those two shapes.
"""

import logging
from typing import Callable, List, Optional

from ...core.ports.fulltext import (
    ExtractedDocument,
    FullTextConfigError,
    FullTextError,
    FullTextTransientError,
    NoOpenAccessVersion,
)

logger = logging.getLogger("academic_hunter.fulltext.sources")


class UnpaywallPdfSource:
    """Unpaywall for the location, the extractor for the bytes."""

    def __init__(self, source, extractor) -> None:
        self.source = source
        self.extractor = extractor

    def __call__(self, doi: str) -> ExtractedDocument:
        location = self.source.locate(doi)
        return self.extractor.extract(self.source.download(location))


class ChainFullTextSource:
    """Try each source in turn; the first that produces a document wins.

    A failure in one source is not a failure of the lookup. Unpaywall frequently
    knows a paper is open while naming no PDF, and Europe PMC may hold it anyway
    — so even a *configuration* error is not grounds for stopping, because the
    sources do not share configuration: an unusable contact address breaks
    Unpaywall and leaves Europe PMC untouched.

    When nothing succeeds the most actionable error is re-raised, so the caller
    can still tell "fix the config" from "there is no copy".
    """

    #: Severity for choosing which failure to report when all of them failed.
    _RANK = {NoOpenAccessVersion: 0, FullTextTransientError: 1, FullTextConfigError: 2}

    def __init__(self, sources: List[Callable[[str], ExtractedDocument]]) -> None:
        if not sources:
            raise ValueError("a chain needs at least one source")
        self.sources = list(sources)

    def __call__(self, doi: str) -> ExtractedDocument:
        worst: Optional[FullTextError] = None

        for source in self.sources:
            name = getattr(source, "__name__", type(source).__name__)
            try:
                document = source(doi)
            except FullTextError as e:
                logger.debug("%s had nothing for %s: %s", name, doi, e)
                worst = self._worse(worst, e)
                continue
            except Exception as e:  # noqa: BLE001 — one source must not stop the chain
                logger.warning("%s failed unexpectedly for %s: %s", name, doi, e)
                worst = self._worse(worst, FullTextTransientError(str(e)))
                continue

            if document.has_text_layer:
                document.source = name
                return document
            # Text was found but is unusable (a scan, an abstract-only record);
            # another source may still have the real thing.
            logger.debug("%s produced no text layer for %s", name, doi)
            worst = self._worse(worst, NoOpenAccessVersion(doi))

        raise worst if worst is not None else NoOpenAccessVersion(doi)

    @classmethod
    def _worse(cls, current: Optional[FullTextError], candidate: FullTextError):
        """Keep the failure that tells the caller the most."""
        if current is None:
            return candidate
        return candidate if cls._RANK.get(type(candidate), 0) > cls._RANK.get(type(current), 0) else current
