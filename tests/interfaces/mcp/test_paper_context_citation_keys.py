"""The citation key `paper_context` hands out must be the one the `.bib` has.

This is a seam test on purpose. `paper_context` lives in the MCP layer and the
bibliography writer in the plugins layer, and each derived the key on its own:
the exporter ran every paper through a `BibtexKeyAllocator`, the tool called
`format_bibtex_key` paper by paper with no allocator at all. Nothing connected
them, so nothing failed when they disagreed — the agent cited a key belonging to
a different paper, and the citation resolved to the wrong reference.

Both sides now call `paper_citation_key`, which derives the key from the paper
alone. The disambiguator is a digest of the paper's own DOI rather than a
position in a collection, so it is the same answer on both sides however
differently they are ordered or filtered.

Against a real ChromaDB, for the same reason as the neighbouring abstract test:
a fake store would return whatever field names the test wrote.
"""

from unittest.mock import patch

import pytest

chromadb = pytest.importorskip("chromadb")

from academic_hunter.core.ports.exporter import ExportContext
from academic_hunter.plugins.exporters.bibtex import BibtexExporter
from academic_hunter.plugins.vector_stores.chroma import ChromaVectorStore

COLLIDING = [
    {"Title": "Echo chambers in social media", "Year": "2024",
     "Abstract": "Polarisation online.", "DOI": "10.1/echo-a"},
    {"Title": "Echo in the courtroom", "Year": "2024",
     "Abstract": "Testimony and memory.", "DOI": "10.1/echo-b"},
]


@pytest.fixture
def store(tmp_path):
    made = ChromaVectorStore(db_dir=str(tmp_path / "chroma"))
    made.index_papers([dict(p) for p in COLLIDING])
    return made


def _keys_in(text: str, pattern: str) -> list:
    import re

    return re.findall(pattern, text)


async def _context(store, mock_ctx, **kwargs) -> str:
    from academic_hunter.interfaces.mcp.tools.writing import paper_context

    with patch(
        "academic_hunter.interfaces.mcp.tools.writing._get_vector_store",
        return_value=store,
    ):
        return await paper_context(mock_ctx, topic="echo", **kwargs)


def _bib_keys_by_title(tmp_path) -> dict:
    BibtexExporter().export(ExportContext(
        papers=[dict(p) for p in COLLIDING],
        stats={"identified": {}, "duplicates_removed": 0, "excluded_year": 0,
               "excluded_anchors": 0, "excluded_technical_score": 0,
               "included_final": len(COLLIDING), "exclusions_by_source": {}},
        settings={}, query_history=[], anchors={}, tech_strings={},
        timestamp="seam", output_dir=tmp_path,
    ))
    written = list(tmp_path.rglob("*.bib"))
    assert written, "the exporter wrote no bibliography"
    text = written[0].read_text(encoding="utf-8")
    return {title: key for key, title in _keys_in(text, r"@article\{([^,]+),\s*\n\s*title = \{([^}]+)\}")}


def _context_keys_by_title(context: str) -> dict:
    pairs = _keys_in(context, r"## \d+\. (.+)\n- \*\*key:\*\* `([^`]+)`")
    return {title.strip(): key for title, key in pairs}


async def test_the_two_papers_get_different_keys_from_the_context(store, mock_ctx):
    """Two distinct papers cannot share one citation key.

    `format_bibtex_key` is derived from the title, and it is not injective — the
    allocator exists for exactly this. The tool skips the allocator, so both
    papers are presented to the agent under the same key and one of the two
    citations must be wrong.
    """
    context = await _context(store, mock_ctx)
    keys = _keys_in(context, r"\*\*key:\*\* `([^`]+)`")

    assert len(keys) == len(COLLIDING), f"expected both papers, got {keys}"
    assert len(set(keys)) == len(COLLIDING), f"keys collide: {keys}"


async def test_each_paper_gets_the_same_key_from_the_tool_and_from_the_bib(store, mock_ctx, tmp_path):
    """The key must belong to *that* paper, not merely exist somewhere.

    Asserting only that the key appears somewhere in the bibliography passes
    even when it is the other paper's key — a citation that resolves, to the
    wrong reference, which is harder to notice than one that fails.
    """
    context = await _context(store, mock_ctx)
    from_tool = _context_keys_by_title(context)
    from_bib = _bib_keys_by_title(tmp_path)

    assert set(from_tool) == set(from_bib), (
        f"the two sides describe different papers: {sorted(from_tool)} vs {sorted(from_bib)}"
    )
    disagree = {t: (from_tool[t], from_bib[t]) for t in from_tool if from_tool[t] != from_bib[t]}
    assert not disagree, f"tool key vs bib key, per paper: {disagree}"
