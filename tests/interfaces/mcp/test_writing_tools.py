"""Tests for the writing MCP tools."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from academic_hunter.interfaces.mcp.exceptions import CitationError, WritingError
from academic_hunter.interfaces.mcp.tools.writing import (
    outline_paper,
    paper_context,
    verify_citations,
)


def _make_run(root: Path, name: str, *, with_stats: bool = True, with_csv: bool = True) -> Path:
    """Create a fake run directory in the layout the pipeline produces."""
    run_dir = root / "results" / name
    run_dir.mkdir(parents=True)
    ts = name.removeprefix("run_")

    if with_stats:
        (run_dir / f"run_stats_{ts}.json").write_text(json.dumps({
            "timestamp": ts,
            "identified": {"OpenAlex": 685, "Crossref": 582},
            "duplicates_removed": 108,
            "excluded_year": 127,
            "excluded_anchors": 833,
            "excluded_technical_score": 75,
            "included_final": 304,
            "exclusions_by_source": {"OpenAlex": {"year": 40, "anchor": 300, "score": 20}},
            "anchors": ["Blockchain", "Interoperability"],
        }))
    if with_csv:
        (run_dir / f"academic_dataset_{ts}.csv").write_text(
            "Title,Abstract,DOI\np1,a,10.1/x\np2,b,10.2/y\n"
        )
    return run_dir


@pytest.fixture
def project(tmp_path, monkeypatch):
    """Point get_project_root at a temporary project with runs."""
    monkeypatch.setattr(
        "academic_hunter.interfaces.mcp.tools.writing.get_project_root",
        lambda: tmp_path,
    )
    return tmp_path


async def test_outline_uses_run_statistics(mock_ctx, project):
    _make_run(project, "run_20260101_120000")
    result = await outline_paper(mock_ctx, paper_type="method", topic="My topic")

    assert "My topic" in result
    assert "Included in final set | 304" in result
    assert "Duplicates removed | 108" in result


async def test_outline_picks_the_most_recent_run(mock_ctx, project):
    _make_run(project, "run_20260101_120000")
    _make_run(project, "run_20260601_120000")
    result = await outline_paper(mock_ctx, paper_type="method")
    assert "run_20260601_120000" in result


async def test_outline_accepts_an_explicit_run(mock_ctx, project):
    _make_run(project, "run_20260101_120000")
    _make_run(project, "run_20260601_120000")
    result = await outline_paper(mock_ctx, paper_type="method", source_run="run_20260101_120000")
    assert "run_20260101_120000" in result


async def test_each_paper_type_produces_its_own_structure(mock_ctx, project):
    _make_run(project, "run_20260101_120000")

    method = await outline_paper(mock_ctx, paper_type="method")
    software = await outline_paper(mock_ctx, paper_type="software")
    survey = await outline_paper(mock_ctx, paper_type="survey")

    assert "## 2 Method" in method
    assert "## Statement of Need" in software
    assert "## 3 Taxonomy" in survey


async def test_unknown_paper_type_raises_with_available_options(mock_ctx, project):
    _make_run(project, "run_20260101_120000")
    with pytest.raises(WritingError, match="method"):
        await outline_paper(mock_ctx, paper_type="nonsense")


async def test_unknown_run_raises(mock_ctx, project):
    _make_run(project, "run_20260101_120000")
    with pytest.raises(WritingError, match="not found"):
        await outline_paper(mock_ctx, paper_type="method", source_run="run_99999999_999999")


async def test_no_runs_at_all_raises(mock_ctx, project):
    (project / "results").mkdir()
    with pytest.raises(WritingError, match="run_search"):
        await outline_paper(mock_ctx, paper_type="method")


async def test_run_without_stats_warns_but_still_produces_structure(mock_ctx, project):
    """Runs predating structured stats must yield a usable skeleton, not an error."""
    _make_run(project, "run_20260101_120000", with_stats=False)
    result = await outline_paper(mock_ctx, paper_type="method", topic="T")

    assert "## 1 Introduction" in result
    assert "predates structured run statistics" in result
    mock_ctx.warning.assert_awaited()


async def test_outline_never_invents_numbers(mock_ctx, project):
    """Without stats there must be no screening table at all — not zeros."""
    _make_run(project, "run_20260101_120000", with_stats=False)
    result = await outline_paper(mock_ctx, paper_type="method")
    assert "Included in final set" not in result


async def test_topic_falls_back_to_run_anchors(mock_ctx, project):
    _make_run(project, "run_20260101_120000")
    result = await outline_paper(mock_ctx, paper_type="method")
    assert "Blockchain, Interoperability" in result


# ── paper_context ────────────────────────────────────────────────────────────


def _fake_store(titles):
    store = MagicMock()
    store.query.return_value = [
        {"title": t, "year": 2024, "doi": f"10.1/{i}", "venue": "V", "source": "S",
         "abstract": "An abstract."}
        for i, t in enumerate(titles)
    ]
    return store


async def test_paper_context_formats_citable_keys(mock_ctx, monkeypatch):
    monkeypatch.setattr(
        "academic_hunter.interfaces.mcp.tools.writing._get_vector_store",
        lambda: _fake_store(["Echo Embeddings for Retrieval"]),
    )
    result = await paper_context(mock_ctx, topic="embeddings")
    assert "`echo2024`" in result
    assert "Echo Embeddings for Retrieval" in result


async def test_paper_context_raises_without_vector_store(mock_ctx, monkeypatch):
    monkeypatch.setattr(
        "academic_hunter.interfaces.mcp.tools.writing._get_vector_store", lambda: None
    )
    with pytest.raises(CitationError, match="[Vv]ector store"):
        await paper_context(mock_ctx, topic="anything")


async def test_paper_context_reports_an_empty_corpus(mock_ctx, monkeypatch):
    monkeypatch.setattr(
        "academic_hunter.interfaces.mcp.tools.writing._get_vector_store",
        lambda: _fake_store([]),
    )
    result = await paper_context(mock_ctx, topic="nothing matches")
    assert "No papers found" in result


async def test_paper_context_clamps_top_k(mock_ctx, monkeypatch):
    store = _fake_store(["A paper"])
    monkeypatch.setattr(
        "academic_hunter.interfaces.mcp.tools.writing._get_vector_store", lambda: store
    )
    await paper_context(mock_ctx, topic="x", top_k=9999)
    assert store.query.call_args.kwargs["top_k"] == 50


# ── verify_citations ─────────────────────────────────────────────────────────


async def test_verify_citations_reports_when_there_is_nothing_to_check(mock_ctx):
    result = await verify_citations(mock_ctx, text="No citations in this paragraph.")
    assert "Nothing to verify" in result


async def test_verify_citations_flags_a_key_missing_from_the_bibliography(
    mock_ctx, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "academic_hunter.interfaces.mcp.tools.writing._get_vector_store", lambda: None
    )
    bib = tmp_path / "paper.bib"
    bib.write_text("@article{real2024,\n  title = {A Real Paper},\n  year = {2024}\n}\n")

    result = await verify_citations(
        mock_ctx, text="Supported [@real2024] but invented [@fake2024].", bib_path=str(bib)
    )
    assert "`fake2024`" in result
    assert "not in the bibliography" in result
    assert "**1 not found**" in result


async def test_verify_citations_raises_on_a_missing_bib_file(mock_ctx, project):
    with pytest.raises(CitationError, match="Bibliography not found"):
        await verify_citations(mock_ctx, text="[@a2024]", bib_path="does/not/exist.bib")


async def test_verify_citations_marks_unverifiable_without_a_bibliography(
    mock_ctx, monkeypatch
):
    """Without a .bib and without a corpus there is no evidence either way."""
    monkeypatch.setattr(
        "academic_hunter.interfaces.mcp.tools.writing._get_vector_store", lambda: None
    )
    result = await verify_citations(mock_ctx, text="See [@something2024].")
    assert "unverifiable" in result.lower()
    assert "NOT_FOUND" not in result
