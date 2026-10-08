"""Tests for search MCP tools (run_search, read_latest_report).

Uses mock_ctx from conftest and patches AcademicHunter and get_project_root.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from academic_hunter.interfaces.mcp.exceptions import MCPToolError, SearchError
from academic_hunter.interfaces.mcp.tools.search import read_latest_report, run_search


class _FakeConnector:
    """Enough of a connector for the coverage report to classify it."""

    def __init__(self, keyword_only, domain=""):
        self.is_keyword_only = keyword_only
        self.domain = domain


@patch("academic_hunter.interfaces.mcp.tools.search.AcademicHunter")
async def test_run_search(mock_hunter_class, mock_ctx):
    mock_instance = MagicMock()
    fake_report_path = os.path.join(os.getcwd(), "results", "RELATORIO_ELITE_123.md")
    mock_instance.run.return_value = fake_report_path
    mock_instance.stats = {"identified": {}, "included_final": 0}
    mock_instance.query_history = []
    mock_instance.connectors = {}
    mock_instance.semantic_screener.degraded = False
    mock_hunter_class.return_value = mock_instance

    result = await run_search(mock_ctx, limit_per_source=2)

    mock_instance.run.assert_called_once_with(limit_per_source=2)
    assert "Search completed successfully" in result
    assert "RELATORIO_ELITE_123.md" in result
    mock_ctx.info.assert_called()
    mock_ctx.report_progress.assert_called()


@patch("academic_hunter.interfaces.mcp.tools.search.AcademicHunter")
async def test_run_search_failure(mock_hunter_class, mock_ctx):
    mock_instance = MagicMock()
    mock_instance.run.side_effect = RuntimeError("API rate limit exceeded")
    mock_hunter_class.return_value = mock_instance

    with pytest.raises(MCPToolError, match="API rate limit exceeded"):
        await run_search(mock_ctx, limit_per_source=2)
    mock_ctx.error.assert_called()


@patch("academic_hunter.interfaces.mcp.tools.search.get_project_root")
async def test_read_latest_report(mock_get_project_root, tmp_path, mock_ctx):
    """read_latest_report must respect get_project_root, not os.getcwd()."""
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    mock_get_project_root.return_value = tmp_path

    report_file = results_dir / "RELATORIO_ELITE_test.md"
    report_file.write_text("# Fake Report\nThis is a test.")

    result = await read_latest_report(mock_ctx)
    assert "Fake Report" in result
    mock_ctx.info.assert_called()


@patch("academic_hunter.interfaces.mcp.tools.search.get_project_root")
async def test_read_latest_report_no_dir(mock_get_project_root, tmp_path, mock_ctx):
    """When no results dir exists, the tool should signal an error."""
    mock_get_project_root.return_value = tmp_path

    with pytest.raises(SearchError, match="No results directory"):
        await read_latest_report(mock_ctx)
    mock_ctx.info.assert_called()


@patch("academic_hunter.interfaces.mcp.tools.search.get_project_root")
async def test_read_latest_report_no_md_files(mock_get_project_root, tmp_path, mock_ctx):
    """Results dir exists but has no markdown files."""
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "data.csv").write_text("a,b,c")
    mock_get_project_root.return_value = tmp_path

    with pytest.raises(SearchError, match="No markdown reports"):
        await read_latest_report(mock_ctx)


@patch("academic_hunter.interfaces.mcp.tools.search.get_project_root")
async def test_read_latest_report_with_offset(mock_get_project_root, tmp_path, mock_ctx):
    """Offset parameter skips the first N characters."""
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    mock_get_project_root.return_value = tmp_path

    report_file = results_dir / "RELATORIO_ELITE_test.md"
    content = "PREFIX" + "ABCDEFGHIJ" * 15
    report_file.write_text(content)

    result = await read_latest_report(mock_ctx, offset=6)
    expected = content[6:]
    assert result == expected
    assert result == "ABCDEFGHIJ" * 15
    assert len(result) == 150
    mock_ctx.info.assert_called()


@patch("academic_hunter.interfaces.mcp.tools.search.get_project_root")
async def test_read_latest_report_custom_max_chars(mock_get_project_root, tmp_path, mock_ctx):
    """Custom max_chars truncates to that exact length."""
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    mock_get_project_root.return_value = tmp_path

    report_file = results_dir / "RELATORIO_ELITE_test.md"
    report_text = "A" * 5000 + "B" * 5000
    report_file.write_text(report_text)

    result = await read_latest_report(mock_ctx, max_chars=100)
    assert len(result) == 100
    assert result == "A" * 100
    mock_ctx.info.assert_called()


@patch("academic_hunter.interfaces.mcp.tools.search.AcademicHunter")
async def test_run_search_refuses_an_empty_config(mock_hunter_class, mock_ctx, tmp_path):
    """The neutral default has no anchors, so a run would query for nothing.

    That is silent degradation: every source is called, nothing scores above the
    threshold, and the tool reports success. The guard turns it into a message
    naming the file and the rung that chose it.
    """
    target = tmp_path / "config.json"
    mock_instance = MagicMock()
    mock_instance.config.is_scorable.return_value = False
    mock_instance.config.config_path = str(target)
    mock_instance.config.config_origin = "packaged_default"
    mock_hunter_class.return_value = mock_instance

    with pytest.raises(MCPToolError) as raised:
        await run_search(mock_ctx, limit_per_source=2)

    assert "packaged_default" in str(raised.value)
    assert str(target) in str(raised.value)
    mock_instance.run.assert_not_called()


@patch("academic_hunter.interfaces.mcp.tools.search.AcademicHunter")
async def test_run_search_proceeds_when_there_is_a_topic(mock_hunter_class, mock_ctx):
    mock_instance = MagicMock()
    mock_instance.config.is_scorable.return_value = True
    mock_instance.run.return_value = os.path.join(os.getcwd(), "results", "RELATORIO_ELITE_1.md")
    mock_instance.stats = {"identified": {}, "included_final": 0}
    mock_instance.query_history = []
    mock_instance.connectors = {}
    mock_instance.semantic_screener.degraded = False
    mock_hunter_class.return_value = mock_instance

    result = await run_search(mock_ctx, limit_per_source=2)

    assert "Search completed successfully" in result
    mock_instance.run.assert_called_once_with(limit_per_source=2)


@patch("academic_hunter.interfaces.mcp.tools.search.AcademicHunter")
async def test_run_search_separates_a_skipped_source_from_an_empty_one(mock_hunter_class, mock_ctx):
    """Both kinds of source report 0, and they are not the same thing.

    In the run that prompted this, ArXiv and Semantic Scholar both showed 0.
    ArXiv was never called -- technical_strings was empty, so the inner loop
    never executed -- while Semantic Scholar was called and found nothing. The
    reply said both had returned zero, and only one of those was a finding.
    """
    mock_instance = MagicMock()
    mock_instance.config.is_scorable.return_value = True
    mock_instance.config.tech_strings = {}
    mock_instance.run.return_value = os.path.join(os.getcwd(), "results", "RELATORIO_ELITE_1.md")
    mock_instance.query_history = [
        {"Source": "Semantic Scholar", "Query": "CBDC"},
        {"Source": "Crossref", "Query": "CBDC"},
    ]
    mock_instance.stats = {
        "identified": {"ArXiv": 0, "Crossref": 20, "Semantic Scholar": 0},
        "included_final": 5,
    }
    mock_instance.connectors = {
        "ArXiv": _FakeConnector(False),
        "Crossref": _FakeConnector(False),
        "Semantic Scholar": _FakeConnector(True),
    }
    mock_instance.semantic_screener.degraded = False
    mock_hunter_class.return_value = mock_instance

    result = await run_search(mock_ctx, limit_per_source=2)

    assert "ArXiv: NOT QUERIED" in result
    assert "Semantic Scholar: 0" in result
    assert "Crossref: 20" in result
    assert "Identified: 20 | Included: 5" in result
    assert "ArXiv never ran a query" in result
    assert "technical_strings is empty" in result


@patch("academic_hunter.interfaces.mcp.tools.search.AcademicHunter")
async def test_run_search_names_the_source_that_could_not_run(mock_hunter_class, mock_ctx):
    """A source skipped for a missing credential says which one, and where.

    Measured: Semantic Scholar without a key took three 429s and was blocked
    mid-run, and the reply said `Semantic Scholar: 0`. The caller could have
    fixed it in one line and had no way to know there was anything to fix --
    while "something else stopped them -- the server log says what" pointed at
    a log the agent never reads.
    """
    mock_instance = MagicMock()
    mock_instance.config.is_scorable.return_value = True
    mock_instance.config.tech_strings = {"Topic": ["cbdc"]}
    mock_instance.run.return_value = os.path.join(os.getcwd(), "results", "RELATORIO_ELITE_1.md")
    mock_instance.query_history = [{"Source": "Crossref", "Query": "CBDC"}]
    mock_instance.stats = {
        "identified": {"Crossref": 20, "Semantic Scholar": 0},
        "included_final": 5,
        "unavailable_sources": {
            "Semantic Scholar": "no API key. Set SEMANTIC_SCHOLAR_API_KEY in the environment."
        },
    }
    mock_instance.connectors = {
        "Crossref": _FakeConnector(False),
        "Semantic Scholar": _FakeConnector(False),
    }
    mock_instance.semantic_screener.degraded = False
    mock_hunter_class.return_value = mock_instance

    result = await run_search(mock_ctx, limit_per_source=2)

    assert "Semantic Scholar: NOT QUERIED" in result
    assert "no API key. Set SEMANTIC_SCHOLAR_API_KEY" in result
    assert "their zeros above are not findings" in result
    assert "something else stopped them" not in result


@patch("academic_hunter.interfaces.mcp.tools.search.AcademicHunter")
async def test_run_search_names_the_source_that_blocked_itself_mid_run(
    mock_hunter_class, mock_ctx
):
    """A source given a thread, throttled, and silenced still reported `0`.

    `unavailable_sources` is computed before any thread starts, so it cannot
    know about this one -- the source only blocks itself once a request has
    already come back 429. And `query_history` records the query *before* it is
    sent (semanticscholar.py:58), so the blocked source is in the history
    exactly as a successful one is.

    Both facts point the same way: `Semantic Scholar: 0` in the reply, with
    nothing anywhere saying the source stopped answering. Measured on the
    published wheel, which has no `unavailable_reason` and no blocked check at
    all -- the run's own `run_stats` has no `unavailable_sources` key.
    """
    mock_instance = MagicMock()
    mock_instance.config.is_scorable.return_value = True
    mock_instance.run.return_value = os.path.join(os.getcwd(), "results", "RELATORIO_ELITE_1.md")
    mock_instance.query_history = [
        {"Source": "Semantic Scholar", "Query": "blockchain"},
        {"Source": "Crossref", "Query": "blockchain"},
    ]
    mock_instance.stats = {
        "identified": {"Crossref": 20, "Semantic Scholar": 0},
        "included_final": 5,
    }
    mock_instance.connectors = {
        "Crossref": _FakeConnector(False, "api.crossref.org"),
        "Semantic Scholar": _FakeConnector(True, "api.semanticscholar.org"),
    }
    mock_instance.blocked_sources = {"api.semanticscholar.org"}
    mock_instance.semantic_screener.degraded = False
    mock_hunter_class.return_value = mock_instance

    result = await run_search(mock_ctx, limit_per_source=2)

    assert "Semantic Scholar: 0 (BLOCKED)" in result
    assert "Crossref: 20" in result
    assert "blocked itself after a rate limit" in result
    assert "counts above are a floor and not a total" in result
    assert "never ran a query" not in result


@patch("academic_hunter.interfaces.mcp.tools.search.AcademicHunter")
async def test_a_blocked_source_keeps_the_papers_it_did_return(mock_hunter_class, mock_ctx):
    """Eight papers and a rate limit is not the same as eight papers.

    The source was answering until it was not, so the count is a floor. Printing
    `BLOCKED` alone would drop papers the run actually found -- the opposite
    mistake from the one this check exists to prevent.
    """
    mock_instance = MagicMock()
    mock_instance.config.is_scorable.return_value = True
    mock_instance.run.return_value = os.path.join(os.getcwd(), "results", "RELATORIO_ELITE_1.md")
    mock_instance.query_history = [{"Source": "CORE", "Query": "blockchain"}]
    mock_instance.stats = {"identified": {"CORE": 8}, "included_final": 2}
    mock_instance.connectors = {"CORE": _FakeConnector(False, "api.core.ac.uk")}
    mock_instance.blocked_sources = {"api.core.ac.uk"}
    mock_instance.semantic_screener.degraded = False
    mock_hunter_class.return_value = mock_instance

    result = await run_search(mock_ctx, limit_per_source=2)

    assert "CORE: 8 (BLOCKED)" in result
    assert "Identified: 8 | Included: 2" in result


@patch("academic_hunter.interfaces.mcp.tools.search.AcademicHunter")
async def test_a_source_that_was_never_blocked_is_reported_plainly(mock_hunter_class, mock_ctx):
    """`blocked_sources` is cleared at the start of every run, and read after it.

    So membership means *this* run's block. A source that has a domain in the
    set from a previous run would be flagged forever, which is the failure this
    guards: `_reset_run_state` clears it, and this asserts the report does not
    invent a block that is not there.
    """
    mock_instance = MagicMock()
    mock_instance.config.is_scorable.return_value = True
    mock_instance.run.return_value = os.path.join(os.getcwd(), "results", "RELATORIO_ELITE_1.md")
    mock_instance.query_history = [{"Source": "CORE", "Query": "blockchain"}]
    mock_instance.stats = {"identified": {"CORE": 8}, "included_final": 2}
    mock_instance.connectors = {"CORE": _FakeConnector(False, "api.core.ac.uk")}
    mock_instance.blocked_sources = {"api.semanticscholar.org"}
    mock_instance.semantic_screener.degraded = False
    mock_hunter_class.return_value = mock_instance

    result = await run_search(mock_ctx, limit_per_source=2)

    assert "CORE: 8" in result
    assert "BLOCKED" not in result


@patch("academic_hunter.interfaces.mcp.tools.search.AcademicHunter")
async def test_a_source_is_not_blamed_for_another_source_s_block(mock_hunter_class, mock_ctx):
    """The set holds domains, the table is keyed by display name.

    Mapping one to the other is the whole job of the check: matching on the name
    would find nothing (the keys never overlap), and skipping the mapping would
    flag every source the moment any one of them was throttled.
    """
    mock_instance = MagicMock()
    mock_instance.config.is_scorable.return_value = True
    mock_instance.run.return_value = os.path.join(os.getcwd(), "results", "RELATORIO_ELITE_1.md")
    mock_instance.query_history = [{"Source": "CORE", "Query": "q"}, {"Source": "ArXiv", "Query": "q"}]
    mock_instance.stats = {"identified": {"CORE": 8, "ArXiv": 12}, "included_final": 2}
    mock_instance.connectors = {
        "CORE": _FakeConnector(False, "api.core.ac.uk"),
        "ArXiv": _FakeConnector(False, "export.arxiv.org"),
    }
    mock_instance.blocked_sources = {"api.core.ac.uk"}
    mock_instance.semantic_screener.degraded = False
    mock_hunter_class.return_value = mock_instance

    result = await run_search(mock_ctx, limit_per_source=2)

    assert "CORE: 8 (BLOCKED)" in result
    assert "ArXiv: 12" in result
    assert "ArXiv: 12 (BLOCKED)" not in result


@patch("academic_hunter.interfaces.mcp.tools.search.AcademicHunter")
async def test_run_search_stays_quiet_when_every_source_was_queried(mock_hunter_class, mock_ctx):
    """The warning has to mean something, so it cannot fire on a healthy run."""
    mock_instance = MagicMock()
    mock_instance.config.is_scorable.return_value = True
    mock_instance.run.return_value = os.path.join(os.getcwd(), "results", "RELATORIO_ELITE_1.md")
    mock_instance.query_history = [{"Source": "ArXiv", "Query": "CBDC"}, {"Source": "Crossref", "Query": "CBDC"}]
    mock_instance.stats = {"identified": {"ArXiv": 12, "Crossref": 8}, "included_final": 3}
    mock_instance.connectors = {"ArXiv": _FakeConnector(False), "Crossref": _FakeConnector(False)}
    mock_instance.semantic_screener.degraded = False
    mock_hunter_class.return_value = mock_instance

    result = await run_search(mock_ctx, limit_per_source=2)

    assert "NOT QUERIED" not in result
    assert "never ran a query" not in result
    assert "Identified: 20 | Included: 3" in result


@patch("academic_hunter.interfaces.mcp.tools.search.AcademicHunter")
async def test_run_search_names_the_anchor_gate_when_nothing_reaches_the_scorer(
    mock_hunter_class, mock_ctx
):
    """``Identified: 11 | Included: 0`` reads as an empty field, and it is not one.

    Measured on a real run: the draft put the topic verbatim in as its only
    anchor, no title carried that phrase, and all 11 papers were dropped at the
    anchor gate. The reply reported the two numbers and stopped, leaving the
    caller to conclude the field was empty.
    """
    mock_instance = MagicMock()
    mock_instance.config.is_scorable.return_value = True
    mock_instance.config.anchors = {"Topic": ["CBDC financial stability"]}
    mock_instance.config.tech_strings = {"CBDC financial stability": ["cbdc"]}
    mock_instance.run.return_value = os.path.join(os.getcwd(), "results", "RELATORIO_ELITE_1.md")
    mock_instance.query_history = [{"Source": "Crossref", "Query": "CBDC"}]
    mock_instance.stats = {
        "identified": {"Crossref": 11},
        "excluded_anchors": 11,
        "excluded_technical_score": 0,
        "included_final": 0,
    }
    mock_instance.connectors = {"Crossref": _FakeConnector(False)}
    mock_hunter_class.return_value = mock_instance

    result = await run_search(mock_ctx, limit_per_source=2)

    assert "Identified: 11 | Included: 0" in result
    assert "Nothing reached the scorer" in result
    assert "CBDC financial stability" in result, "the terms to widen are not in the reply"
    assert "11 of the 11 identified papers" in result


@patch("academic_hunter.interfaces.mcp.tools.search.AcademicHunter")
async def test_run_search_stays_quiet_when_the_scorer_did_run(mock_hunter_class, mock_ctx):
    """Anchors that drop some papers are the normal case, not the warning.

    These are the numbers from the same field with the anchors widened: 20
    identified, 7 dropped at the anchor gate, 5 for a low score, 6 included.
    """
    mock_instance = MagicMock()
    mock_instance.config.is_scorable.return_value = True
    mock_instance.run.return_value = os.path.join(os.getcwd(), "results", "RELATORIO_ELITE_1.md")
    mock_instance.query_history = [{"Source": "Crossref", "Query": "CBDC"}]
    mock_instance.stats = {
        "identified": {"Crossref": 20},
        "excluded_anchors": 7,
        "excluded_technical_score": 5,
        "included_final": 6,
    }
    mock_instance.connectors = {"Crossref": _FakeConnector(False)}
    mock_instance.semantic_screener.degraded = False
    mock_hunter_class.return_value = mock_instance

    result = await run_search(mock_ctx, limit_per_source=2)

    assert "Identified: 20 | Included: 6" in result
    assert "Nothing reached the scorer" not in result
    assert "Semantic scoring was degraded" not in result


@patch("academic_hunter.interfaces.mcp.tools.search.AcademicHunter")
async def test_run_search_says_when_the_semantic_scoring_degraded(mock_hunter_class, mock_ctx):
    """The pipeline logs this at the end of the run; the agent reads the reply.

    A run whose embedding fell back to zero vectors still finishes and still
    reports scores -- every semantic one of them 0.0. Without this the caller
    has a report that looks like any other.
    """
    mock_instance = MagicMock()
    mock_instance.config.is_scorable.return_value = True
    mock_instance.run.return_value = os.path.join(os.getcwd(), "results", "RELATORIO_ELITE_1.md")
    mock_instance.query_history = [{"Source": "Crossref", "Query": "CBDC"}]
    mock_instance.stats = {"identified": {"Crossref": 20}, "included_final": 6}
    mock_instance.connectors = {"Crossref": _FakeConnector(False)}
    mock_instance.semantic_screener.degraded = True
    mock_hunter_class.return_value = mock_instance

    result = await run_search(mock_ctx, limit_per_source=2)

    assert "Semantic scoring was degraded" in result
    assert "keyword-only" in result
