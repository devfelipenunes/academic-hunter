"""Tests for summarize_paper tool."""
import pytest
from unittest.mock import patch, MagicMock


async def test_summarize_paper_no_abstract(mock_ctx):
    """Returns message when abstract not found."""
    from academic_hunter.interfaces.mcp.tools.summarize import summarize_paper

    with patch("academic_hunter.interfaces.mcp.tools.summarize.AcademicHunter") as m_h:
        instance = m_h.return_value
        instance.fetch_abstract_by_doi.return_value = None
        result = await summarize_paper(mock_ctx, "10.1000/missing")
    assert "not available" in result or "Not found" in result


async def test_summarize_paper_short_abstract(mock_ctx):
    """Returns message when abstract is too short."""
    from academic_hunter.interfaces.mcp.tools.summarize import summarize_paper

    with patch("academic_hunter.interfaces.mcp.tools.summarize.AcademicHunter") as m_h:
        instance = m_h.return_value
        instance.fetch_abstract_by_doi.return_value = "Short."
        result = await summarize_paper(mock_ctx, "10.1000/short")
    assert "too short" in result.lower()


async def test_summarize_paper_few_sentences(mock_ctx):
    """Returns full abstract when it has fewer sentences than requested."""
    from academic_hunter.interfaces.mcp.tools.summarize import summarize_paper

    abstract = "This paper introduces a novel method for deep learning in natural language processing. We evaluate the approach on multiple standard benchmarks and achieve state-of-the-art results. The proposed architecture reduces computational cost significantly while maintaining high accuracy."
    n_sentences = 5

    with patch("academic_hunter.interfaces.mcp.tools.summarize.AcademicHunter") as m_h:
        instance = m_h.return_value
        instance.fetch_abstract_by_doi.return_value = abstract
        with patch("sentence_transformers.SentenceTransformer") as m_st:
            mock_model = MagicMock()

            def encode_side_effect(texts):
                import numpy as np
                if isinstance(texts, list):
                    return [np.full(384, 0.5, dtype=np.float32) for _ in texts]
                return [np.full(384, 0.5, dtype=np.float32)]

            mock_model.encode.side_effect = encode_side_effect
            m_st.return_value = mock_model
            result = await summarize_paper(mock_ctx, "10.1000/test", num_sentences=n_sentences)

    assert "Abstract Summary" in result
    assert "deep learning" in result.lower()


async def test_summarize_paper_clamps_num_sentences(mock_ctx):
    """Clamps num_sentences to max 8."""
    from academic_hunter.interfaces.mcp.tools.summarize import summarize_paper

    abstract = ". ".join([
        "This paper presents a novel deep learning architecture for natural language processing tasks",
        "We evaluate the proposed method on multiple benchmark datasets including GLUE and SuperGLUE",
        "Our approach achieves state-of-the-art results while requiring significantly less computational resources",
        "The key innovation is a sparse attention mechanism that reduces the quadratic complexity to linear",
        "We also introduce a new training procedure that improves convergence speed by up to 3x",
        "Extensive ablation studies confirm the effectiveness of each component of our architecture",
        "We release our code and pre-trained models to facilitate reproducibility and future research",
        "The results demonstrate that our method generalizes well across diverse domains and languages",
        "Qualitative analysis reveals that the model learns interpretable representations at multiple levels",
        "This work opens up new directions for efficient transformer architectures in resource-constrained settings",
    ])

    with patch("academic_hunter.interfaces.mcp.tools.summarize.AcademicHunter") as m_h:
        instance = m_h.return_value
        instance.fetch_abstract_by_doi.return_value = abstract
        with patch("sentence_transformers.SentenceTransformer") as m_st:
            mock_model = MagicMock()

            def encode_side_effect(texts):
                import numpy as np
                if isinstance(texts, list):
                    return [np.full(384, 0.5, dtype=np.float32) for _ in texts]
                return [np.full(384, 0.5, dtype=np.float32)]

            mock_model.encode.side_effect = encode_side_effect
            m_st.return_value = mock_model
            result = await summarize_paper(mock_ctx, "10.1000/test", num_sentences=50)

    assert "Extractive Summary" in result


async def test_summarize_paper_import_error(mock_ctx):
    """Returns message when dependencies missing."""
    from academic_hunter.interfaces.mcp.tools.summarize import summarize_paper

    abstract = "This paper introduces a novel method for deep learning in natural language processing tasks. We evaluate the proposed approach on multiple standard benchmark datasets. The architecture reduces computational cost while maintaining high accuracy and performance. These results demonstrate significant improvements over existing methods."

    with patch("academic_hunter.interfaces.mcp.tools.summarize.AcademicHunter") as m_h:
        instance = m_h.return_value
        instance.fetch_abstract_by_doi.return_value = abstract
        with patch("sentence_transformers.SentenceTransformer") as m_st:
            m_st.side_effect = ImportError("No sentence-transformers")
            result = await summarize_paper(mock_ctx, "10.1000/test")

    assert "academic-hunter[ml]" in result


async def test_summarize_paper_invalid_doi(mock_ctx):
    """Returns error for invalid DOI format."""
    from academic_hunter.interfaces.mcp.tools.summarize import summarize_paper

    with patch("academic_hunter.interfaces.mcp.tools.summarize.validate_doi") as m_val:
        m_val.side_effect = ValueError("Invalid DOI")
        result = await summarize_paper(mock_ctx, "not-a-doi")

    assert "Invalid DOI" in result
