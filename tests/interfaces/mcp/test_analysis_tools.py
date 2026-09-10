"""Tests for analysis MCP tools (trending_topics, compare_papers, export_report).

Uses mock_ctx from conftest and patches ChromaVectorStore / AcademicHunter / requests
in the relevant tool modules.
"""

import json
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from pathlib import Path

from academic_hunter.interfaces.mcp.tools.trending import trending_topics
from academic_hunter.interfaces.mcp.tools.comparison import compare_papers
from academic_hunter.interfaces.mcp.tools.export import export_report
from academic_hunter.interfaces.mcp.tools.summarize import summarize_paper
from academic_hunter.interfaces.mcp.exceptions import DiscoveryError, SearchError, MCPToolError


# ── trending_topics ───────────────────────────────────────────────────────


async def test_trending_topics(mock_ctx):
    """Success path — vector store returns papers whose titles share bigrams."""
    mock_papers = [
        {"title": "Deep Learning for Natural Language Processing"},
        {"title": "Deep Learning in Computer Vision Applications"},
        {"title": "Advances in Deep Learning for Healthcare"},
        {"title": "Transformer Models for Natural Language Understanding"},
        {"title": "Reinforcement Learning for Robotics Control"},
        {"title": "Multi Agent Reinforcement Learning Systems"},
        {"title": "Quantum Machine Learning Algorithms"},
    ]

    with patch(
        "academic_hunter.interfaces.mcp.tools.trending._get_vector_store"
    ) as m_get:
        store = MagicMock()
        store.query.return_value = mock_papers
        m_get.return_value = store

        result = await trending_topics(mock_ctx, days=30, min_papers=2)

        assert "Trending Research Topics" in result
        assert "deep learning" in result.lower()
        assert "7 papers analyzed" in result or "7" in result.split("Total papers analyzed")[-1][:5]
        store.query.assert_called_once()
        mock_ctx.info.assert_called()


async def test_trending_topics_no_results(mock_ctx):
    """Empty vector store returns the expected message."""
    with patch(
        "academic_hunter.interfaces.mcp.tools.trending._get_vector_store"
    ) as m_get:
        store = MagicMock()
        store.query.return_value = []
        m_get.return_value = store

        result = await trending_topics(mock_ctx)

        assert "No trending topics found" in result
        assert "Index papers first" in result


async def test_trending_topics_store_unavailable(mock_ctx):
    """When the vector store cannot be initialised, return a meaningful message."""
    with patch(
        "academic_hunter.interfaces.mcp.tools.trending._get_vector_store",
        return_value=None,
    ):
        result = await trending_topics(mock_ctx)

        assert "Vector store not available" in result
        assert "Index papers first" in result
        mock_ctx.error.assert_called()


async def test_trending_topics_below_threshold(mock_ctx):
    """No bigram meets the min_papers threshold."""
    mock_papers = [
        {"title": "Quantum Computing Applications"},
        {"title": "Deep Learning in Biology"},
    ]

    with patch(
        "academic_hunter.interfaces.mcp.tools.trending._get_vector_store"
    ) as m_get:
        store = MagicMock()
        store.query.return_value = mock_papers
        m_get.return_value = store

        result = await trending_topics(mock_ctx, min_papers=3)

        assert "No trending topics found" in result
        assert "Index papers first" in result


# ── compare_papers ────────────────────────────────────────────────────────


async def test_compare_papers(mock_ctx):
    """Success path — both papers retrieved from Semantic Scholar."""
    mock_response_a = {
        "title": "Paper Alpha",
        "year": 2023,
        "abstract": "This paper explores deep reinforcement learning for robotics navigation.",
    }
    mock_response_b = {
        "title": "Paper Beta",
        "year": 2024,
        "abstract": "Recent advances in deep reinforcement learning for autonomous systems.",
    }

    with patch("academic_hunter.interfaces.mcp.tools.comparison.AcademicHunter") as m_hunter:
        hunter_instance = m_hunter.return_value
        hunter_instance.fetch_abstract_by_doi.return_value = ""

        with patch(
            "requests.get"
        ) as m_get:
            def _side_effect(url, **kwargs):
                resp = MagicMock()
                resp.raise_for_status.return_value = None
                if "DOI:10.1000/alpha" in url:
                    resp.json.return_value = mock_response_a
                elif "DOI:10.1000/beta" in url:
                    resp.json.return_value = mock_response_b
                else:
                    resp.json.return_value = {}
                return resp

            m_get.side_effect = _side_effect

            result = await compare_papers(mock_ctx, "10.1000/alpha", "10.1000/beta")

            assert "Paper Comparison" in result
            assert "Paper Alpha" in result
            assert "Paper Beta" in result
            assert "2023" in result
            assert "2024" in result
            assert "Shared Keywords" in result
            assert "deep" in result or "reinforcement" in result or "learning" in result
            mock_ctx.info.assert_called()


async def test_compare_papers_one_not_found(mock_ctx):
    """Graceful handling when one paper's metadata cannot be retrieved."""
    mock_response_a = {
        "title": "Paper Alpha",
        "year": 2023,
        "abstract": "Deep learning methods for NLP.",
    }

    with patch("academic_hunter.interfaces.mcp.tools.comparison.AcademicHunter") as m_hunter:
        hunter_instance = m_hunter.return_value
        hunter_instance.fetch_abstract_by_doi.return_value = ""

        with patch(
            "requests.get"
        ) as m_get:
            def _side_effect(url, **kwargs):
                resp = MagicMock()
                resp.raise_for_status.return_value = None
                if "DOI:10.1000/alpha" in url:
                    resp.json.return_value = mock_response_a
                else:
                    # Simulate empty response for missing paper
                    resp.json.return_value = {}
                return resp

            m_get.side_effect = _side_effect

            result = await compare_papers(mock_ctx, "10.1000/alpha", "10.1000/missing")

            assert "Paper Comparison" in result
            assert "Paper Alpha" in result or "Unknown Title" in result
            mock_ctx.info.assert_called()


async def test_compare_papers_api_error(mock_ctx):
    """API failures propagate as DiscoveryError."""
    with patch(
        "requests.get"
    ) as m_get:
        from requests.exceptions import RequestException

        m_get.side_effect = RequestException("Network error")

        with pytest.raises(DiscoveryError) as exc_info:
            await compare_papers(mock_ctx, "10.1000/a", "10.1000/b")

        assert "Network error" in str(exc_info.value)
        mock_ctx.error.assert_called()


# ── export_report ─────────────────────────────────────────────────────────


async def test_export_report_csv(mock_ctx, tmp_path):
    """CSV export writes a valid file with paper data."""
    mock_papers = [
        {"Title": "Paper One", "DOI": "10.1000/one", "Year": 2023},
        {"Title": "Paper Two", "DOI": "10.1000/two", "Year": 2024},
    ]

    with patch(
        "academic_hunter.interfaces.mcp.tools.export.get_project_root",
        return_value=tmp_path,
    ):
        with patch(
            "academic_hunter.interfaces.mcp.tools.export.AcademicHunter"
        ) as m_hunter:
            hunter_instance = m_hunter.return_value
            type(hunter_instance).consolidated_results = PropertyMock(
                return_value={f"p{i}": p for i, p in enumerate(mock_papers)}
            )

            output_file = str(tmp_path / "test_export.csv")
            result = await export_report(mock_ctx, format="csv", output_path=output_file)

            assert "Successfully exported 2 papers" in result
            assert Path(output_file).exists()
            content = Path(output_file).read_text()
            assert "Title" in content
            assert "Paper One" in content
            assert "Paper Two" in content
            mock_ctx.info.assert_called()


async def test_export_report_json(mock_ctx, tmp_path):
    """JSON export writes a valid JSON array with paper data."""
    mock_papers = [
        {"Title": "Paper One", "DOI": "10.1000/one", "Year": 2023},
    ]

    with patch(
        "academic_hunter.interfaces.mcp.tools.export.get_project_root",
        return_value=tmp_path,
    ):
        with patch(
            "academic_hunter.interfaces.mcp.tools.export.AcademicHunter"
        ) as m_hunter:
            hunter_instance = m_hunter.return_value
            type(hunter_instance).consolidated_results = PropertyMock(
                return_value={"p0": mock_papers[0]}
            )

            output_file = str(tmp_path / "test_export.json")
            result = await export_report(mock_ctx, format="json", output_path=output_file)

            assert "Successfully exported 1 papers" in result
            assert Path(output_file).exists()
            data = json.loads(Path(output_file).read_text())
            assert len(data) == 1
            assert data[0]["Title"] == "Paper One"
            mock_ctx.info.assert_called()


async def test_export_report_no_results(mock_ctx, tmp_path):
    """Empty results return a helpful message.

    The disk read is patched away rather than pointed at an empty tmp_path:
    `_load_latest_papers` resolves the project root through `_utils`, not
    through `export`, so patching the latter left it reading the repository's
    real `results/` and exporting 135 papers instead of none.
    """
    with (
        patch(
            "academic_hunter.interfaces.mcp.tools.export.AcademicHunter"
        ) as m_hunter,
        patch(
            "academic_hunter.interfaces.mcp.tools.export.get_project_root"
        ) as m_root,
        patch(
            "academic_hunter.interfaces.mcp.tools.export._load_latest_papers",
            return_value=[],
        ),
    ):
        hunter_instance = m_hunter.return_value
        type(hunter_instance).consolidated_results = PropertyMock(return_value={})
        m_root.return_value = tmp_path  # no CSV files exist here

        result = await export_report(mock_ctx)

        assert "No search results to export" in result
        mock_ctx.info.assert_called()


async def test_export_report_unsupported_format(mock_ctx):
    """Unsupported format string returns an error message."""
    with patch(
        "academic_hunter.interfaces.mcp.tools.export.AcademicHunter"
    ) as m_hunter:
        hunter_instance = m_hunter.return_value
        type(hunter_instance).consolidated_results = PropertyMock(
            return_value={"p0": {"Title": "Test"}}
        )

        result = await export_report(mock_ctx, format="xml")

        assert "Unsupported format" in result
        assert "csv" in result
        assert "json" in result
        mock_ctx.error.assert_called()


async def test_export_report_default_output_path(mock_ctx, tmp_path):
    """When output_path is None, file is written to results/ with a timestamp."""
    mock_papers = [{"Title": "Paper One", "Year": 2023}]

    with patch(
        "academic_hunter.interfaces.mcp.tools.export.get_project_root",
        return_value=tmp_path,
    ):
        with patch(
            "academic_hunter.interfaces.mcp.tools.export.AcademicHunter"
        ) as m_hunter:
            hunter_instance = m_hunter.return_value
            type(hunter_instance).consolidated_results = PropertyMock(
                return_value={"p0": mock_papers[0]}
            )

            result = await export_report(mock_ctx, format="csv")

            assert "Successfully exported 1 papers" in result
            # Should have written to results/export_{timestamp}.csv
            exported_files = list((tmp_path / "results").glob("export_*.csv"))
            assert len(exported_files) == 1
            mock_ctx.info.assert_called()


async def test_export_report_bibtex(mock_ctx, tmp_path):
    """BibTeX export produces a valid BibTeX file with expected fields."""
    mock_papers = [
        {"Title": "Paper One", "DOI": "10.1000/one", "Year": 2023,
         "Authors": "Author A and Author B", "Source": "Journal X",
         "Abstract": "A groundbreaking study."},
        {"Title": "Paper Two", "DOI": "10.1000/two", "Year": 2024,
         "Authors": "Author C", "Source": "Journal Y"},
    ]

    with patch(
        "academic_hunter.interfaces.mcp.tools.export.get_project_root",
        return_value=tmp_path,
    ):
        with patch(
            "academic_hunter.interfaces.mcp.tools.export.AcademicHunter"
        ) as m_hunter:
            hunter_instance = m_hunter.return_value
            type(hunter_instance).consolidated_results = PropertyMock(
                return_value={f"p{i}": p for i, p in enumerate(mock_papers)}
            )

            output_file = str(tmp_path / "test_export.bib")
            result = await export_report(mock_ctx, format="bibtex", output_path=output_file)

            assert "Successfully exported 2 papers" in result
            assert Path(output_file).exists()
            content = Path(output_file).read_text()
            assert "@article{" in content
            assert "author" in content
            assert "title" in content
            assert "Paper One" in content
            assert "10.1000/one" in content
            mock_ctx.info.assert_called()


async def test_export_report_ris(mock_ctx, tmp_path):
    """RIS export produces a valid RIS file with expected fields."""
    mock_papers = [
        {"Title": "Paper One", "DOI": "10.1000/one", "Year": 2023,
         "Authors": ["Author A", "Author B"], "Source": "Journal X"},
    ]

    with patch(
        "academic_hunter.interfaces.mcp.tools.export.get_project_root",
        return_value=tmp_path,
    ):
        with patch(
            "academic_hunter.interfaces.mcp.tools.export.AcademicHunter"
        ) as m_hunter:
            hunter_instance = m_hunter.return_value
            type(hunter_instance).consolidated_results = PropertyMock(
                return_value={"p0": mock_papers[0]}
            )

            output_file = str(tmp_path / "test_export.ris")
            result = await export_report(mock_ctx, format="ris", output_path=output_file)

            assert "Successfully exported 1 papers" in result
            assert Path(output_file).exists()
            content = Path(output_file).read_text()
            assert "TY  - JOUR" in content
            assert "TI  - Paper One" in content
            assert "PY  - 2023" in content
            assert "AU  - Author A" in content
            assert "AU  - Author B" in content
            mock_ctx.info.assert_called()


async def test_export_report_write_error(mock_ctx):
    """File write errors raise SearchError."""
    with patch(
        "academic_hunter.interfaces.mcp.tools.export.AcademicHunter"
    ) as m_hunter:
        hunter_instance = m_hunter.return_value
        type(hunter_instance).consolidated_results = PropertyMock(
            return_value={"p0": {"Title": "Test"}}
        )

        with pytest.raises(SearchError) as exc_info:
            await export_report(mock_ctx, format="csv", output_path="/nonexistent_dir/file.csv")

        assert "Cannot save file" in str(exc_info.value)
        mock_ctx.error.assert_called()


# ── summarize_paper ─────────────────────────────────────────────────


async def test_summarize_paper(mock_ctx):
    """Returns extractive summary from abstract."""
    mock_abstract = "This is the first sentence of the paper. Here is the second one discussing methods. The third sentence presents the key findings. Fourth sentence discusses implications. Fifth sentence concludes the work."

    with patch("academic_hunter.interfaces.mcp.tools.summarize.AcademicHunter") as m_hunter:
        instance = m_hunter.return_value
        instance.fetch_abstract_by_doi.return_value = mock_abstract

        with patch("sentence_transformers.SentenceTransformer") as m_st:
            model = MagicMock()
            import numpy as np
            model.encode.return_value = np.array([[0.1, 0.2], [0.3, 0.4], [0.5, 0.6], [0.7, 0.8], [0.9, 1.0]])
            m_st.return_value = model

            result = await summarize_paper(mock_ctx, "10.1234/test", num_sentences=3)
            assert "Extractive Summary" in result
            assert "Centroid + MMR" in result
            mock_ctx.info.assert_called()


async def test_summarize_paper_not_found(mock_ctx):
    """Graceful when paper not found."""
    with patch("academic_hunter.interfaces.mcp.tools.summarize.AcademicHunter") as m_hunter:
        instance = m_hunter.return_value
        instance.fetch_abstract_by_doi.return_value = None
        result = await summarize_paper(mock_ctx, "10.1234/unknown")
        assert "not available" in result or "Could not fetch" in result


async def test_summarize_paper_short_abstract(mock_ctx):
    """Graceful when abstract is too short."""
    with patch("academic_hunter.interfaces.mcp.tools.summarize.AcademicHunter") as m_hunter:
        instance = m_hunter.return_value
        instance.fetch_abstract_by_doi.return_value = "Short."
        result = await summarize_paper(mock_ctx, "10.1234/short")
        assert "too short" in result.lower()


# ── find_related_papers ─────────────────────────────────────────────────


async def test_find_related_papers_basic(mock_ctx):
    """Returns related papers from semantic search."""
    from academic_hunter.interfaces.mcp.tools.related import find_related_papers

    with patch(
        "academic_hunter.interfaces.mcp.tools.related._get_vector_store"
    ) as m_get:
        store = MagicMock()
        store.query.return_value = [
            {"title": "Paper A", "semantic_relevance": 0.95, "year": 2024},
        ]
        m_get.return_value = store

        result = await find_related_papers(mock_ctx, "test query", top_k=5)
        assert "Paper A" in result
        assert "95" in result
        mock_ctx.info.assert_called()


async def test_find_related_papers_no_results(mock_ctx):
    """Returns message when no related papers found."""
    from academic_hunter.interfaces.mcp.tools.related import find_related_papers

    with patch(
        "academic_hunter.interfaces.mcp.tools.related._get_vector_store"
    ) as m_get:
        store = MagicMock()
        store.query.return_value = []
        m_get.return_value = store

        result = await find_related_papers(mock_ctx, "unknown topic")
        assert "No related papers found" in result


async def test_find_related_papers_no_store(mock_ctx):
    """Returns error when vector store unavailable."""
    from academic_hunter.interfaces.mcp.tools.related import find_related_papers

    with patch(
        "academic_hunter.interfaces.mcp.tools.related._get_vector_store",
        return_value=None,
    ):
        result = await find_related_papers(mock_ctx, "test")
        assert "not available" in result.lower()
