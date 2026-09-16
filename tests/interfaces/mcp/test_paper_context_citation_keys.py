"""The citation key `paper_context` hands out must be the one the `.bib` has.

This is a seam test on purpose. `paper_context` lives in the MCP layer and the
bibliography writer in the plugins layer, and each derives the key on its own:
the exporter runs every paper through a `BibtexKeyAllocator`, the tool calls
`format_bibtex_key` paper by paper with no allocator at all. Nothing connects
them, so nothing fails when they disagree — the agent just cites a key that
belongs to a different paper, and the citation resolves to the wrong reference.

Against a real ChromaDB, for the same reason as the neighbouring abstract test:
a fake store would return whatever field names the test wrote.

**Measured defect, marked xfail — the fix is a decision, not a patch.** With two
papers whose title stem and year coincide, the tool hands the agent `echo2024`
for both, while the `.bib` has `echo2024` and `echo2024-2`. The second citation
therefore resolves to the *other* paper, which is harder to notice than one that
fails outright.

It does not close with a one-line change, because the two sides cannot agree by
construction: the allocator disambiguates **by position**, and the tool sees a
similarity-ranked subset while the exporter sees the run's whole set in its own
order. Giving the tool its own allocator stops two papers sharing a key inside
one context and still leaves the key pointing at a different paper in the `.bib`.

What would actually close it is a disambiguator derived from the paper rather
than from the set — a short DOI suffix, say — so both sides can compute the same
key without coordinating. That changes the citation keys in existing
manuscripts, so it is the author's call, not a mechanical fix.
"""

from unittest.mock import patch

import pytest

chromadb = pytest.importorskip("chromadb")

from academic_hunter.core.ports.exporter import ExportContext
from academic_hunter.plugins.exporters.bibtex import BibtexExporter
from academic_hunter.plugins.vector_stores.chroma import ChromaVectorStore

#: Same first meaningful word, same year — so `format_bibtex_key` derives the
#: same stem for both. The allocator is what keeps them apart in the `.bib`.
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


@pytest.mark.xfail(
    strict=True,
    reason="known: the tool allocates no keys, so colliding titles share one — "
           "see the module docstring for the open decision",
)
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


@pytest.mark.xfail(
    strict=True,
    reason="known: measured `echo2024` from the tool against `echo2024-2` in the "
           ".bib — the citation resolves, to the other paper",
)
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
