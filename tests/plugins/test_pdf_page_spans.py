"""PDF extraction preserves a reversible mapping from text ranges to pages."""

import sys
from types import SimpleNamespace

from academic_hunter.plugins.fulltext.pdf import PdfExtractor


def test_pdf_extractor_records_page_text_offsets(monkeypatch):
    page_texts = ["A" * 300, "B" * 300]

    class Reader:
        is_encrypted = False
        pages = [SimpleNamespace(extract_text=lambda text=text: text) for text in page_texts]

    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=lambda stream: Reader()))

    document = PdfExtractor().extract(b"pdf bytes")

    assert document.text == page_texts[0] + "\n" + page_texts[1]
    assert document.page_count == 2
    assert [(span.start, span.end, span.page) for span in document.page_spans] == [
        (0, 300, 1),
        (301, 601, 2),
    ]
