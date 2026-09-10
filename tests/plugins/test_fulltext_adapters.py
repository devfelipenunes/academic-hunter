"""Tests for the full-text adapters: Unpaywall, PDF extraction, and the cache.

No network: every HTTP call is mocked, and the PDFs are built here.
"""

from unittest.mock import MagicMock, patch

import pytest

from academic_hunter.core.ports.fulltext import (
    FullTextConfigError,
    FullTextTransientError,
    NoOpenAccessVersion,
    OpenAccessLocation,
)
from academic_hunter.plugins.fulltext.cache import CachedFullTextSource, PdfCache
from academic_hunter.plugins.fulltext.unpaywall import UnpaywallSource, fetch_record

API = "academic_hunter.plugins.fulltext.unpaywall.requests.get"


def response(status=200, payload=None, headers=None, body=None):
    mock = MagicMock()
    mock.status_code = status
    mock.json.return_value = payload if payload is not None else {}
    mock.headers = headers or {}
    if body is not None:
        mock.iter_content.return_value = [body]
    return mock


def make_pdf(text: str = "Hello world") -> bytes:
    """A minimal one-page PDF carrying ``text``, with a correct xref table."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


# ── Unpaywall: locating ─────────────────────────────────────────────────────


def test_locate_returns_the_best_pdf_location():
    payload = {
        "is_oa": True,
        "best_oa_location": {
            "url_for_pdf": "https://example.org/a.pdf",
            "host_type": "repository",
            "version": "acceptedVersion",
            "license": "cc-by",
        },
    }
    with patch(API, return_value=response(200, payload)):
        location = UnpaywallSource("me@example.com").locate("10.1/x")

    assert location.url == "https://example.org/a.pdf"
    assert location.host == "repository"
    assert location.license == "cc-by"


def test_locate_prefers_a_location_that_names_a_pdf():
    """`best_oa_location` is Unpaywall's pick for reliability, and it is often
    the publisher landing page with a null `url_for_pdf` — while another entry
    in the same record does name one.

    Measured against the live API: using only `best` turned "there is a PDF in
    the repository" into "download failed".
    """
    payload = {
        "is_oa": True,
        "best_oa_location": {
            "url": "https://publisher.example/landing",
            "url_for_pdf": None,
            "host_type": "publisher",
        },
        "oa_locations": [
            {"url": "https://publisher.example/landing", "url_for_pdf": None},
            {
                "url": "https://repo.example/a",
                "url_for_pdf": "https://repo.example/a.pdf",
                "host_type": "repository",
                "license": "cc-by",
            },
        ],
    }
    with patch(API, return_value=response(200, payload)):
        location = UnpaywallSource("a@b.c").locate("10.1/x")

    assert location.url == "https://repo.example/a.pdf"
    assert location.host == "repository"
    assert location.license == "cc-by"


def test_locate_falls_back_to_a_landing_url_when_no_pdf_is_named():
    """Some records genuinely offer no direct PDF; the download checks the bytes."""
    payload = {
        "is_oa": True,
        "best_oa_location": {"url": "https://publisher.example/landing"},
        "oa_locations": [{"url": "https://publisher.example/landing"}],
    }
    with patch(API, return_value=response(200, payload)):
        assert UnpaywallSource("a@b.c").locate("10.1/x").url == (
            "https://publisher.example/landing"
        )


def test_locate_falls_back_to_the_landing_url():
    payload = {"is_oa": True, "best_oa_location": {"url": "https://example.org/landing"}}
    with patch(API, return_value=response(200, payload)):
        assert UnpaywallSource("a@b.c").locate("10.1/x").url == "https://example.org/landing"


def test_no_open_access_is_not_an_error():
    """It is the common case, and the run has to count it as such."""
    with patch(API, return_value=response(200, {"is_oa": False})):
        with pytest.raises(NoOpenAccessVersion):
            UnpaywallSource("a@b.c").locate("10.1/x")


def test_an_unknown_doi_is_no_open_access():
    with patch(API, return_value=response(404)):
        with pytest.raises(NoOpenAccessVersion):
            UnpaywallSource("a@b.c").locate("10.1/x")


def test_a_refused_email_is_a_config_error():
    """Every later call would fail the same way, so the caller has to stop."""
    with patch(API, return_value=response(422)):
        with pytest.raises(FullTextConfigError):
            UnpaywallSource("a@b.c").locate("10.1/x")


def test_a_server_error_is_transient():
    with patch(API, return_value=response(503)):
        with pytest.raises(FullTextTransientError):
            UnpaywallSource("a@b.c").locate("10.1/x")


def test_a_network_failure_is_transient():
    import requests

    with patch(API, side_effect=requests.RequestException("boom")):
        with pytest.raises(FullTextTransientError):
            UnpaywallSource("a@b.c").locate("10.1/x")


def test_an_unusable_contact_email_is_refused_at_construction():
    """Before any request, not after hundreds of them."""
    with pytest.raises(FullTextConfigError):
        UnpaywallSource("")
    with pytest.raises(FullTextConfigError):
        UnpaywallSource("not-an-email")


# ── Unpaywall: downloading ──────────────────────────────────────────────────


def test_download_returns_the_bytes():
    pdf = make_pdf()
    with patch(API, return_value=response(200, body=pdf)):
        assert UnpaywallSource("a@b.c").download(OpenAccessLocation("https://x/y.pdf")) == pdf


def test_download_refuses_an_oversized_body_by_header():
    with patch(API, return_value=response(200, headers={"Content-Length": "999999999"}, body=b"%PDF-")):
        with pytest.raises(FullTextTransientError, match="cap"):
            UnpaywallSource("a@b.c").download(OpenAccessLocation("https://x/y.pdf"), max_bytes=100)


def test_download_refuses_an_oversized_body_while_streaming():
    """A lying or absent Content-Length must not turn into an unbounded read."""
    with patch(API, return_value=response(200, body=b"%PDF-" + b"x" * 5000)):
        with pytest.raises(FullTextTransientError, match="cap"):
            UnpaywallSource("a@b.c").download(OpenAccessLocation("https://x/y.pdf"), max_bytes=100)


def test_download_rejects_html_masquerading_as_a_pdf():
    """A publisher landing page answers 200 with HTML."""
    with patch(API, return_value=response(200, body=b"<!doctype html><html>...")):
        with pytest.raises(FullTextTransientError, match="did not return a PDF"):
            UnpaywallSource("a@b.c").download(OpenAccessLocation("https://x/y.pdf"))


# ── PDF extraction ──────────────────────────────────────────────────────────


def test_extract_reads_the_text_layer():
    pytest.importorskip("pypdf")
    from academic_hunter.plugins.fulltext.pdf import PdfExtractor

    # Over the 500-char threshold, below which the file is treated as a scan.
    body = "Latency in distributed ledgers. " * 30
    document = PdfExtractor().extract(make_pdf(body))

    assert "Latency in distributed ledgers" in document.text
    assert document.page_count == 1
    assert document.has_text_layer is True


def test_a_short_text_layer_is_reported_as_a_scan():
    """No OCR: the caller needs to know the text is not there."""
    pytest.importorskip("pypdf")
    from academic_hunter.plugins.fulltext.pdf import PdfExtractor

    document = PdfExtractor().extract(make_pdf("hi"))

    assert document.has_text_layer is False


def test_a_corrupt_file_is_transient_not_fatal():
    pytest.importorskip("pypdf")
    from academic_hunter.plugins.fulltext.pdf import PdfExtractor

    with pytest.raises(FullTextTransientError):
        PdfExtractor().extract(b"%PDF-1.4\nthis is not a pdf at all")


def test_a_missing_pypdf_says_which_extra_to_install(monkeypatch):
    from academic_hunter.plugins.fulltext.pdf import PdfExtractor

    monkeypatch.setitem(__import__("sys").modules, "pypdf", None)
    with pytest.raises(FullTextConfigError, match="fulltext"):
        PdfExtractor().extract(b"%PDF-")


# ── Cache ───────────────────────────────────────────────────────────────────


def test_the_cache_round_trips(tmp_path):
    cache = PdfCache(tmp_path)

    assert cache.get("https://x/y.pdf") is None
    cache.put("https://x/y.pdf", b"%PDF-abc")
    assert cache.get("https://x/y.pdf") == b"%PDF-abc"


def test_the_cache_distinguishes_urls(tmp_path):
    cache = PdfCache(tmp_path)
    cache.put("https://x/one.pdf", b"%PDF-one")
    cache.put("https://x/two.pdf", b"%PDF-two")

    assert cache.get("https://x/one.pdf") == b"%PDF-one"
    assert cache.get("https://x/two.pdf") == b"%PDF-two"


def test_a_second_download_never_reaches_the_network(tmp_path):
    """This is what makes a repeat run offline, and it lives in the wiring."""
    source = MagicMock()
    source.download.return_value = b"%PDF-real"
    cached = CachedFullTextSource(source, PdfCache(tmp_path))
    location = OpenAccessLocation("https://x/y.pdf")

    first = cached.download(location)
    second = cached.download(location)

    assert first == second == b"%PDF-real"
    assert source.download.call_count == 1, "the second call should hit the cache"


def test_the_cache_does_not_swallow_a_failed_download(tmp_path):
    source = MagicMock()
    source.download.side_effect = FullTextTransientError("nope")
    cached = CachedFullTextSource(source, PdfCache(tmp_path))

    with pytest.raises(FullTextTransientError):
        cached.download(OpenAccessLocation("https://x/y.pdf"))
    assert PdfCache(tmp_path).get("https://x/y.pdf") is None


def test_locate_is_not_cached(tmp_path):
    """Whether an OA copy exists is cheap to ask and can change between runs."""
    source = MagicMock()
    source.locate.return_value = OpenAccessLocation("https://x/y.pdf")
    cached = CachedFullTextSource(source, PdfCache(tmp_path))

    cached.locate("10.1/x")
    cached.locate("10.1/x")

    assert source.locate.call_count == 2
