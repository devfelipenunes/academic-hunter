"""Tests for internal helper functions used across tools."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


# ── _coci_request ──────────────────────────────────────────────────


async def test_coci_request_success(mock_ctx):
    """_coci_request returns parsed JSON on success."""
    from academic_hunter.interfaces.mcp.tools.citations import _coci_request

    mock_response = MagicMock()
    mock_response.json.return_value = [{"count": "5"}]

    with patch("academic_hunter.interfaces.mcp.tools.citations.requests.get") as m_get:
        m_get.return_value = mock_response
        result = await _coci_request("citation-count", "10.1234/test")
        assert result == [{"count": "5"}]
        m_get.assert_called_once()


async def test_coci_request_raises_on_error(mock_ctx):
    """_coci_request raises on HTTP error."""
    from academic_hunter.interfaces.mcp.tools.citations import _coci_request
    import requests

    with patch("academic_hunter.interfaces.mcp.tools.citations.requests.get") as m_get:
        m_get.side_effect = requests.RequestException("HTTP 500")
        with pytest.raises(requests.RequestException):
            await _coci_request("citation-count", "10.1234/test")


# ── _request_with_retry ────────────────────────────────────────────


async def test_request_with_retry_success(mock_ctx):
    """Retry succeeds on first attempt."""
    from academic_hunter.interfaces.mcp.tools.discovery import _request_with_retry

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("academic_hunter.interfaces.mcp.tools.discovery.requests.get") as m_get:
        m_get.return_value = mock_response
        result = await _request_with_retry("http://test.com")
        assert result == mock_response


async def test_request_with_retry_retries_on_429(mock_ctx):
    """Retry retries on 429 then succeeds."""
    from academic_hunter.interfaces.mcp.tools.discovery import _request_with_retry

    fail_response = MagicMock()
    fail_response.status_code = 429
    success_response = MagicMock()
    success_response.status_code = 200

    with patch("academic_hunter.interfaces.mcp.tools.discovery.requests.get") as m_get:
        m_get.side_effect = [fail_response, success_response]
        result = await _request_with_retry("http://test.com", max_retries=2, base_delay=0.01)
        assert result == success_response
        assert m_get.call_count == 2


async def test_request_with_retry_exhausts_retries(mock_ctx):
    """Retry raises after exhausting retries on persistent 429."""
    from academic_hunter.interfaces.mcp.tools.discovery import _request_with_retry
    import requests

    fail_response = MagicMock()
    fail_response.status_code = 429
    fail_response.raise_for_status.side_effect = requests.HTTPError("429 Too Many Requests")

    with patch("academic_hunter.interfaces.mcp.tools.discovery.requests.get") as m_get:
        m_get.return_value = fail_response
        with pytest.raises(requests.RequestException):
            await _request_with_retry("http://test.com", max_retries=2, base_delay=0.01)


# ── _extract_bigrams ───────────────────────────────────────────────


def test_extract_bigrams_returns_bigrams():
    """Extracts meaningful bigrams from title."""
    from academic_hunter.interfaces.mcp.tools._utils import _STOPWORDS
    from academic_hunter.interfaces.mcp.tools.trending import _extract_bigrams

    result = _extract_bigrams("Deep Learning for NLP", _STOPWORDS)
    assert "deep learning" in result
    assert "learning for" not in result  # 'for' is stopword


def test_extract_bigrams_ignores_stopwords():
    """Bigrams containing stopwords are excluded."""
    from academic_hunter.interfaces.mcp.tools._utils import _STOPWORDS
    from academic_hunter.interfaces.mcp.tools.trending import _extract_bigrams

    result = _extract_bigrams("The impact of AI on society", _STOPWORDS)
    assert all("the" not in bg for bg in result)
    assert all("of" not in bg for bg in result)
    assert all("on" not in bg for bg in result)


# ── _extract_meta ──────────────────────────────────────────────────


def test_extract_meta_parses_openai_response():
    """Extracts metadata from OpenAIRE-style nested response."""
    from academic_hunter.interfaces.mcp.tools.openaire import _extract_meta

    oaf = {
        "title": [{"@classid": "main title", "$": "Test Paper Title"}],
        "creator": [{"$": "Author One"}, {"$": "Author Two"}],
        "dateofacceptance": {"$": "2024-03-15"},
        "pid": [{"@classid": "doi", "$": "10.1000/test"}],
        "bestaccessright": {"@classid": "OPEN ACCESS"},
        "project": [{"funder": {"$": "European Commission"}}],
    }
    meta = _extract_meta(oaf)
    assert meta["title"] == "Test Paper Title"
    assert meta["authors"] == "Author One; Author Two"
    assert "2024" in meta["date"]
    assert meta["doi"] == "10.1000/test"
    assert "OA" in meta["oa"]
    assert "European Commission" in meta["funder"]


def test_extract_meta_empty_fallback():
    """Returns fallback values when fields are missing."""
    from academic_hunter.interfaces.mcp.tools.openaire import _extract_meta

    meta = _extract_meta({})
    assert meta["title"] == ""
    assert meta["authors"] == "?"
    assert meta["doi"] == ""
    assert meta["oa"] == ""
    assert meta["funder"] == ""


# ── _utils: get_project_root ──────────────────────────────────────


def test_get_project_root_finds_pyproject(tmp_path):
    """get_project_root returns the parent of pyproject.toml."""
    from academic_hunter.interfaces.mcp.tools import _utils

    pkg_init = tmp_path / "src" / "academic_hunter" / "__init__.py"
    pkg_init.parent.mkdir(parents=True)
    pkg_init.write_text("")
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[project]")

    with patch.object(_utils, "pkg") as mock_pkg:
        mock_pkg.__file__ = str(pkg_init)
        root = _utils.get_project_root()
    assert root == tmp_path


def test_get_project_root_fallback_cwd():
    """get_project_root falls back to cwd when no pyproject.toml."""
    from pathlib import Path
    from academic_hunter.interfaces.mcp.tools import _utils
    import os

    tmp = __import__("tempfile").mkdtemp()
    fake_pkg = __import__("types").SimpleNamespace()
    fake_pkg.__file__ = os.path.join(tmp, "pkg", "__init__.py")
    os.makedirs(os.path.dirname(fake_pkg.__file__), exist_ok=True)
    with open(fake_pkg.__file__, "w"):
        pass

    with patch.object(_utils, "pkg", fake_pkg):
        root = _utils.get_project_root()
    assert root == Path.cwd()


# ── _utils: _get_vector_store ────────────────────────────────────


def test_get_vector_store_disabled(mock_ctx):
    """Returns None when the store cannot be built.

    The failure is raised by ``ChromaVectorStore``, not by ``AcademicHunter``:
    the store no longer builds a hunter to derive its path — that cost a whole
    tool-call's worth of setup per call, and with the hunter mocked it produced
    a MagicMock repr that ChromaDB turned into a real directory.
    """
    from academic_hunter.interfaces.mcp.tools import _utils

    with patch.object(_utils, "ChromaVectorStore") as m_store:
        m_store.side_effect = Exception("chromadb unavailable")
        result = _utils._get_vector_store()
    assert result is None


def test_get_vector_store_does_not_build_a_hunter():
    """The path comes from the project root; no hunter is constructed."""
    from pathlib import Path

    from academic_hunter.interfaces.mcp.tools import _utils

    with patch.object(_utils, "ChromaVectorStore") as m_store, \
         patch.object(_utils, "AcademicHunter") as m_hunter, \
         patch.object(_utils, "get_project_root", return_value=Path("/tmp/proj")):
        _utils._get_vector_store()

    m_hunter.assert_not_called()
    assert m_store.call_args.kwargs["db_dir"] == str(
        Path("/tmp/proj") / ".academic_hunter" / "chroma_db"
    )


# ── _utils: _make_hunter ─────────────────────────────────────────


def test_make_hunter(mock_ctx):
    """Creates an AcademicHunter with project-root output."""
    from pathlib import Path
    from academic_hunter.interfaces.mcp.tools import _utils

    mock_hunter = MagicMock()
    with patch.object(_utils, "AcademicHunter") as m_h:
        with patch.object(_utils, "get_project_root") as m_root:
            m_root.return_value = Path("/tmp/test_project")
            m_h.return_value = mock_hunter
            result = _utils._make_hunter()
    m_h.assert_called_once_with(output_dir="/tmp/test_project/results")
    assert result == mock_hunter


# ── _write_bibtex ──────────────────────────────────────────────────


def test_write_bibtex_creates_entries(tmp_path):
    """Writes BibTeX entries to file."""
    from academic_hunter.interfaces.mcp.tools.export import _write_bibtex

    papers = [
        {"Title": "Paper One", "DOI": "10.1000/one", "Authors": "Author A", "Year": 2024},
    ]
    out = tmp_path / "test.bib"
    _write_bibtex(papers, str(out))

    content = out.read_text()
    assert "@article{" in content
    assert "Paper One" in content
    assert "Author A" in content
    assert "2024" in content


def test_write_bibtex_empty_fields(tmp_path):
    """Writes BibTeX entries when optional fields are empty."""
    from academic_hunter.interfaces.mcp.tools.export import _write_bibtex

    papers = [
        {"Title": "", "DOI": "", "Authors": "", "Year": "", "Source": "", "URL": "", "Abstract": ""},
    ]
    out = tmp_path / "empty.bib"
    _write_bibtex(papers, str(out))

    content = out.read_text()
    assert "@article{" in content
    assert "}" in content


def test_write_bibtex_no_doi_key(tmp_path):
    """Falls back to paper_N key when DOI is empty."""
    from academic_hunter.interfaces.mcp.tools.export import _write_bibtex

    papers = [{"Title": "No DOI Paper"}]
    out = tmp_path / "test.bib"
    _write_bibtex(papers, str(out))

    content = out.read_text()
    assert "paper_1" in content


# ── _write_ris ─────────────────────────────────────────────────────


def test_write_ris_creates_entries(tmp_path):
    """Writes RIS entries to file."""
    from academic_hunter.interfaces.mcp.tools.export import _write_ris

    papers = [
        {"Title": "Paper One", "DOI": "10.1000/one", "Authors": ["Author A"], "Year": 2024},
    ]
    out = tmp_path / "test.ris"
    _write_ris(papers, str(out))

    content = out.read_text()
    assert "TY  - JOUR" in content
    assert "TI  - Paper One" in content
    assert "DO  - 10.1000/one" in content
    assert "PY  - 2024" in content


def test_write_ris_string_author(tmp_path):
    """Writes RIS with string author (not list)."""
    from academic_hunter.interfaces.mcp.tools.export import _write_ris

    papers = [
        {"Title": "Paper", "Authors": "Single Author"},
    ]
    out = tmp_path / "test.ris"
    _write_ris(papers, str(out))

    content = out.read_text()
    assert "AU  - Single Author" in content


def test_write_ris_empty_papers(tmp_path):
    """Writes empty RIS when no papers provided."""
    from academic_hunter.interfaces.mcp.tools.export import _write_ris

    out = tmp_path / "empty.ris"
    _write_ris([], str(out))

    content = out.read_text()
    assert content.strip() == ""
