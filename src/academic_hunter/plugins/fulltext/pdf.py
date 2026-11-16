"""PDF text extraction, backed by ``pypdf``.

``pypdf`` rather than PyMuPDF: the latter is AGPL-3.0 and this project is MIT, so
declaring it would put an AGPL dependency inside the metadata of an MIT
distribution. It stays supported as an *undeclared* adapter behind the same port,
for anyone who accepts the licence and installs it themselves.
"""

import logging

from ...core.ports.fulltext import (
    ExtractedDocument,
    FullTextConfigError,
    FullTextTransientError,
    PageSpan,
)

logger = logging.getLogger("academic_hunter.fulltext.pdf")

MIN_TEXT_CHARS = 500


class PdfExtractor:
    """Turning PDF bytes into text, backed by ``pypdf``."""

    def extract(self, pdf_bytes: bytes) -> ExtractedDocument:
        """Text of every page, joined.

        Raises:
            FullTextConfigError: ``pypdf`` is not installed — the extra is
                optional, and the message says which one to install.
            FullTextTransientError: the file could not be parsed.
        """
        try:
            from pypdf import PdfReader
        except ImportError as e:
            raise FullTextConfigError(
                "pypdf is not installed. Install the extra: "
                "pip install 'academic-hunter[fulltext]'"
            ) from e

        try:
            reader = PdfReader(_stream(pdf_bytes))
            if reader.is_encrypted:
                raise FullTextTransientError("PDF is encrypted")
            pages = [page.extract_text() or "" for page in reader.pages]
        except FullTextTransientError:
            raise
        except Exception as e:
            raise FullTextTransientError(f"Could not parse the PDF: {e}") from e

        raw_parts = []
        spans = []
        cursor = 0
        for page_number, page_text in enumerate(pages, start=1):
            start = cursor
            raw_parts.append(page_text)
            cursor += len(page_text)
            spans.append(PageSpan(start=start, end=cursor, page=page_number))
            if page_number < len(pages):
                raw_parts.append("\n")
                cursor += 1

        raw_text = "".join(raw_parts)
        trim_start = len(raw_text) - len(raw_text.lstrip())
        trim_end = len(raw_text.rstrip())
        text = raw_text[trim_start:trim_end]
        page_spans = [
            PageSpan(
                start=max(0, span.start - trim_start),
                end=min(len(text), span.end - trim_start),
                page=span.page,
            )
            for span in spans
            if span.end >= trim_start and span.start <= trim_end
        ]
        has_layer = len(text) >= MIN_TEXT_CHARS
        if not has_layer:
            logger.info(
                "PDF yielded %d chars, below the %d threshold — treating as a scan.",
                len(text), MIN_TEXT_CHARS,
            )
        return ExtractedDocument(
            text=text,
            page_count=len(pages),
            has_text_layer=has_layer,
            page_spans=page_spans,
        )


def _stream(pdf_bytes: bytes):
    """A reader over the bytes, since ``PdfReader`` wants a file-like object."""
    from io import BytesIO

    return BytesIO(pdf_bytes)
