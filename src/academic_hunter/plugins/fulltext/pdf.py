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
)

logger = logging.getLogger("academic_hunter.fulltext.pdf")

#: Below this, the PDF carries no usable text layer — it is a scan. No OCR is
#: attempted: tesseract is not a dependency and adding it would end the
#: zero-cost, offline character of the pipeline.
MIN_TEXT_CHARS = 500


class PdfExtractor:
    """A :class:`TextExtractorPort` backed by ``pypdf``."""

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
            # Encrypted PDFs raise on access rather than on construction, so the
            # decrypt call is what surfaces a password-protected file.
            if reader.is_encrypted:
                raise FullTextTransientError("PDF is encrypted")
            pages = [page.extract_text() or "" for page in reader.pages]
        except FullTextTransientError:
            raise
        except Exception as e:
            raise FullTextTransientError(f"Could not parse the PDF: {e}") from e

        text = "\n".join(pages).strip()
        has_layer = len(text) >= MIN_TEXT_CHARS
        if not has_layer:
            logger.info(
                "PDF yielded %d chars, below the %d threshold — treating as a scan.",
                len(text), MIN_TEXT_CHARS,
            )
        return ExtractedDocument(text=text, page_count=len(pages), has_text_layer=has_layer)


def _stream(pdf_bytes: bytes):
    """A reader over the bytes, since ``PdfReader`` wants a file-like object."""
    from io import BytesIO

    return BytesIO(pdf_bytes)
