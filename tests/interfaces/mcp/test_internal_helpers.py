"""Tests for internal helper functions used across tools."""

import threading
from unittest.mock import MagicMock, patch

import pytest

from academic_hunter.core.infra.openalex import OPENALEX_DEFAULT_DELAY
from academic_hunter.core.infra.transport import HttpTransport


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
    import requests

    from academic_hunter.interfaces.mcp.tools.citations import _coci_request

    with patch("academic_hunter.interfaces.mcp.tools.citations.requests.get") as m_get:
        m_get.side_effect = requests.RequestException("HTTP 500")
        with pytest.raises(requests.RequestException):
            await _coci_request("citation-count", "10.1234/test")


def _openalex_test_response(status_code=200, payload=None, retry_after=None):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload if payload is not None else {}
    response.headers = {"Retry-After": retry_after} if retry_after else {}
    return response


class _FakeClock:
    """A stand-in for the ``time`` module, patched onto ``_utils.time`` only.

    Patching the real module's ``time``/``sleep`` reaches every thread in the
    process, and a ``side_effect`` list that runs out raises StopIteration inside
    whatever called it next. ``sleep`` advancing the clock is also what makes the
    pacing assertion arithmetic rather than a guess.
    """

    def __init__(self, now=1000.0):
        self.now = now
        self.slept: list = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def test_openalex_get_returns_the_payload(mock_openalex):
    """One request, and the parsed body comes back."""
    from academic_hunter.interfaces.mcp.tools import _utils

    with patch.object(_utils.requests, "get") as m_get:
        m_get.return_value = _openalex_test_response(payload={"results": [1, 2]})
        assert _utils._openalex_get_sync("/works", {"search": "x"}) == {"results": [1, 2]}

    assert m_get.call_count == 1
    assert m_get.call_args.kwargs["params"]["search"] == "x"
    assert m_get.call_args.args[0] == "https://api.openalex.org/works"


def _with_mcp_transport(monkeypatch, clock, delay: float = 0.0) -> None:
    """Point the MCP path at a transport this test drives.

    The pacing and the retry belong to ``core.infra.transport`` now, and these
    tests are about the waiting the shared fixture exists to remove — so they
    build their own, with the arithmetic clock and without the no-op sleep.
    """
    from academic_hunter.core.infra import transport as transport_module
    from academic_hunter.interfaces.mcp.tools import _utils

    transport = HttpTransport(
        lock=threading.Lock(),
        semaphore=threading.Semaphore(2),
        pacing_delays={},
        last_request_by_domain={},
        blocked_sources=set(),
        default_delay=delay,
        block_sources=False,
        sleep=clock.sleep,
    )
    monkeypatch.setattr(transport_module, "time", clock)
    monkeypatch.setattr(_utils, "_openalex_transport", lambda: transport)
    monkeypatch.setattr(_utils, "_openalex_headers_and_params", lambda: ({}, {}))


def test_openalex_get_retries_a_429_then_succeeds(monkeypatch):
    """The wait is the one the API asked for, taken by the shared policy."""
    from academic_hunter.interfaces.mcp.tools import _utils

    clock = _FakeClock()
    _with_mcp_transport(monkeypatch, clock)

    with patch.object(_utils.requests, "get") as m_get:
        m_get.side_effect = [
            _openalex_test_response(429, retry_after="1"),
            _openalex_test_response(200, {"ok": True}),
        ]
        assert _utils._openalex_get_sync("/works") == {"ok": True}

    assert m_get.call_count == 2
    assert clock.slept == [1.0]


def test_openalex_get_makes_at_most_attempts_requests(monkeypatch):
    """A spent budget costs `attempts` requests, not one more.

    The helper this replaced slept through its loop and then issued a further
    request *outside* it, so an exhausted retry cost four calls where the
    parameter promised three. How long each wait is now belongs to the shared
    policy; what this holds it to is the count, and that nothing is waited after
    the last attempt.
    """
    import requests

    from academic_hunter.interfaces.mcp.tools import _utils

    spent = _openalex_test_response(429, retry_after="1")
    spent.raise_for_status.side_effect = requests.HTTPError("429 Too Many Requests")

    clock = _FakeClock()
    _with_mcp_transport(monkeypatch, clock)

    with patch.object(_utils.requests, "get") as m_get:
        m_get.return_value = spent
        with pytest.raises(requests.HTTPError):
            _utils._openalex_get_sync("/works", attempts=3)

    assert m_get.call_count == 3
    assert clock.slept == [1.0, 1.0]


def test_openalex_get_paces_successive_calls(monkeypatch):
    """Two calls in a row are held apart by the delay the source declares.

    The half-second constant this used to assert went with the private policy:
    the MCP path now paces by ``OPENALEX_DEFAULT_DELAY``, the same number the
    pipeline's connector uses, so this imports it rather than restating it. If
    a second half-second ever reappears here, this is what fails.
    """
    from academic_hunter.interfaces.mcp.tools import _utils

    clock = _FakeClock()
    _with_mcp_transport(monkeypatch, clock, delay=OPENALEX_DEFAULT_DELAY)

    with patch.object(_utils.requests, "get") as m_get:
        m_get.return_value = _openalex_test_response()
        _utils._openalex_get_sync("/works")
        assert clock.slept == [], "the first call should not be paced"

        _utils._openalex_get_sync("/works")

    assert clock.slept == [OPENALEX_DEFAULT_DELAY]


def test_openalex_key_prefers_the_environment(monkeypatch):
    """The env var wins, so a key can be used without writing it to disk."""
    from academic_hunter.core.infra.config import openalex_key

    settings = {"api_keys": {"openalex": "from-file"}, "openalex_api_key": "flat"}
    assert openalex_key(settings) == "from-file"

    monkeypatch.setenv("OPENALEX_API_KEY", "from-env")
    assert openalex_key(settings) == "from-env"

    monkeypatch.delenv("OPENALEX_API_KEY")
    assert openalex_key({"openalex_api_key": "flat"}) == "flat"
    assert openalex_key({}) == ""


def test_extract_bigrams_returns_bigrams():
    """Extracts meaningful bigrams from title."""
    from academic_hunter.interfaces.mcp.tools._utils import _STOPWORDS
    from academic_hunter.interfaces.mcp.tools.trending import _extract_bigrams

    result = _extract_bigrams("Deep Learning for NLP", _STOPWORDS)
    assert "deep learning" in result
    assert "learning for" not in result
    assert "learning nlp" not in result


def test_extract_bigrams_does_not_stitch_across_a_removed_stopword():
    """A stopword separates two words; removing it does not join them.

    Pairing whatever survives the stopword filter made "Deep Learning for NLP"
    yield "learning nlp" and "AI for ML is cool stuff" yield "for cool", both of
    which read as phrases a field uses and neither of which appeared in a title.
    """
    from academic_hunter.interfaces.mcp.tools._utils import _STOPWORDS
    from academic_hunter.interfaces.mcp.tools.trending import _extract_bigrams

    assert "learning nlp" not in _extract_bigrams("Deep Learning for NLP", _STOPWORDS)
    assert "for cool" not in _extract_bigrams("AI for ML is cool stuff", set())


def test_extract_bigrams_keeps_words_that_are_actually_adjacent():
    """The words a bigram joins were next to each other in the title."""
    from academic_hunter.interfaces.mcp.tools._utils import _STOPWORDS
    from academic_hunter.interfaces.mcp.tools.trending import _extract_bigrams

    result = _extract_bigrams(
        "Efficient KV Cache Quantization for Inference", _STOPWORDS
    )
    assert "cache quantization" in result


def test_extract_bigrams_ignores_stopwords():
    """Bigrams containing stopwords are excluded."""
    from academic_hunter.interfaces.mcp.tools._utils import _STOPWORDS
    from academic_hunter.interfaces.mcp.tools.trending import _extract_bigrams

    result = _extract_bigrams("The impact of AI on society", _STOPWORDS)
    assert all("the" not in bg for bg in result)
    assert all("of" not in bg for bg in result)
    assert all("on" not in bg for bg in result)


def test_extract_meta_parses_openai_response():
    """Extracts metadata from OpenAIRE-style nested response."""
    from academic_hunter.interfaces.mcp.tools.sources import _openaire_meta as _extract_meta

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
    from academic_hunter.interfaces.mcp.tools.sources import _openaire_meta as _extract_meta

    meta = _extract_meta({})
    assert meta["title"] == ""
    assert meta["authors"] == "?"
    assert meta["doi"] == ""
    assert meta["oa"] == ""
    assert meta["funder"] == ""


def test_get_project_root_is_the_resolved_data_dir(tmp_path, monkeypatch):
    """The explicit data dir wins, so get_project_root is the resolver's answer."""
    from academic_hunter.core.infra import paths
    from academic_hunter.interfaces.mcp.tools import _utils

    monkeypatch.setenv(paths.DATA_ENV, str(tmp_path))
    assert _utils.get_project_root() == tmp_path


def test_get_project_root_honours_a_project_marker(tmp_path, monkeypatch):
    """A directory holding .academic_hunter is the project, not the checkout."""
    from academic_hunter.core.infra import paths
    from academic_hunter.interfaces.mcp.tools import _utils

    monkeypatch.delenv(paths.DATA_ENV, raising=False)
    monkeypatch.delenv(paths.PROJECT_ENV, raising=False)
    (tmp_path / paths.DATA_DIRNAME).mkdir()
    monkeypatch.chdir(tmp_path)
    assert _utils.get_project_root() == tmp_path


def _fake_project(tmp_path):
    """A results/ tree with two runs and one file that is not a run."""
    run = tmp_path / "results" / "run_20260910_120000"
    run.mkdir(parents=True)
    (run / "academic_dataset_20260910_120000.csv").write_text("Title\nA\n")
    (run / "run_stats_20260910_120000.json").write_text("{}")

    old = tmp_path / "results" / "run_20260601_090000"
    old.mkdir(parents=True)
    (old / "academic_dataset_20260601_090000.csv").write_text("Title\nB\n")

    (tmp_path / "results" / "run_stats_test_stats.json").write_text("{}")
    return tmp_path


def test_latest_run_dir_ignores_a_file_that_is_not_a_run(tmp_path):
    """Measured defect: `run_stats_test_stats.json` became "the latest run".

    It is written into `results/` by a test, carries no run stamp, and used to
    win on ctime — which made `fulltext_status` report on a file that is not a
    run at all.
    """
    from academic_hunter.interfaces.mcp.tools import _utils

    root = _fake_project(tmp_path)
    with patch.object(_utils, "get_project_root", return_value=root):
        assert _utils._latest_run_dir().name == "run_20260910_120000"


def test_latest_run_dir_is_none_without_runs(tmp_path):
    from academic_hunter.interfaces.mcp.tools import _utils

    (tmp_path / "results").mkdir()
    with patch.object(_utils, "get_project_root", return_value=tmp_path):
        assert _utils._latest_run_dir() is None


def test_load_latest_papers_reads_the_newest_run(tmp_path):
    """The stamp in the filename decides, not the file's change time."""
    from academic_hunter.interfaces.mcp.tools import _utils

    root = _fake_project(tmp_path)
    older = root / "results" / "run_20260601_090000" / "academic_dataset_20260601_090000.csv"
    import os

    os.utime(older, (9_000_000_000, 9_000_000_000))

    with patch.object(_utils, "get_project_root", return_value=root):
        papers = _utils._load_latest_papers()

    assert papers and papers[0]["Title"] == "A"


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
