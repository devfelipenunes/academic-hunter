"""`paper_context` tem de mostrar o abstract que o store devolveu.

Contra um ChromaDB real, de propósito: o defeito era um **nome de campo** — o
store devolve `abstract_preview` e a tool lia `abstract` — e um store falso
devolveria o nome que o teste escrevesse, escondendo exatamente isso.
"""

from unittest.mock import patch

import pytest

chromadb = pytest.importorskip("chromadb")

from academic_hunter.plugins.vector_stores.chroma import ChromaVectorStore

ABSTRACT = "We measure distributed ledger throughput under sustained load."


@pytest.fixture
def store(tmp_path):
    made = ChromaVectorStore(db_dir=str(tmp_path / "chroma"))
    made.index_papers([{"Title": "Ledgers at scale", "Abstract": ABSTRACT}])
    return made


async def _context(store, mock_ctx, **kwargs):
    from academic_hunter.interfaces.mcp.tools.writing import paper_context

    with patch(
        "academic_hunter.interfaces.mcp.tools.writing._get_vector_store",
        return_value=store,
    ):
        return await paper_context(mock_ctx, topic="ledger throughput", **kwargs)


async def test_the_abstract_the_store_returned_reaches_the_context(store, mock_ctx):
    """One reads `abstract_preview`, the other reads `abstract`.

    Nothing failed when they disagreed: the field was simply absent, and every
    paper in the agent's context arrived without its abstract.
    """
    context = await _context(store, mock_ctx)

    assert "Ledgers at scale" in context, "the paper itself is missing"
    assert "distributed ledger throughput" in context, (
        "the abstract the store returned never reached the context"
    )


async def test_the_generated_key_is_the_one_the_bibliography_will_use(store, mock_ctx):
    """A key the agent is told to cite verbatim has to exist in the exported .bib."""
    from academic_hunter.core.writing import format_bibtex_key

    context = await _context(store, mock_ctx)

    assert f"`{format_bibtex_key('Ledgers at scale', '')}`" in context
