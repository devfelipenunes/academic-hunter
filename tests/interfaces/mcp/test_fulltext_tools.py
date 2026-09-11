"""Tests for the full-text MCP tools.

The store is mocked here; the pieces that need a real ChromaDB (the metadata
round-trip, the `where` filter) are covered by `tests/plugins/test_chunk_store.py`.
What these tests are for is the reporting: the failure mode this feature has is
not a crash, it is a number that reads as a measurement when nothing was
measured.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from academic_hunter.core.ports.fulltext import (
    ExtractedDocument,
    NoOpenAccessVersion,
)
from academic_hunter.interfaces.mcp.tools import fulltext as ft

LONG_TEXT = (
    "Abstract\nThis paper studies ledgers.\n\n"
    "1. Introduction\n" + " ".join(f"alpha{i}" for i in range(300)) + "\n\n"
    "2. Methods\n" + " ".join(f"beta{i}" for i in range(300))
)


class FakeStore:
    """Satisfies ``ChunkStorePort`` structurally, and records the calls."""

    def __init__(self, hits=None, count=0, already=()):
        self.hits = hits or []
        self.count = count
        self.already = set(already)
        self.indexed = []
        self.deleted = []
        self.queries = []

    def index_chunks(self, chunks, collection_name="paper_chunks"):
        self.indexed.append(list(chunks))
        return True

    def query_chunks(self, prompt, top_k=10, collection_name="paper_chunks"):
        self.queries.append((prompt, top_k, collection_name))
        return self.hits[:top_k]

    def has_chunks(self, parent_id, collection_name="paper_chunks"):
        return parent_id in self.already

    def delete_chunks(self, parent_id, collection_name="paper_chunks"):
        self.deleted.append(parent_id)
        return 1

    def collection_stats(self, name="papers"):
        return {"name": name, "count": self.count}


def make_run(tmp_path, statuses=None, counters=None, name="run_20260910_120000"):
    """A run directory holding a dataset and/or a run_stats file."""
    run = tmp_path / "results" / name
    run.mkdir(parents=True)

    if statuses is not None:
        rows = ["Title,DOI,_full_text_status"] + [
            f"Paper {i},10.1/{i},{status}" for i, status in enumerate(statuses)
        ]
        (run / f"academic_dataset_{name[4:]}.csv").write_text(
            "\n".join(rows), encoding="utf-8"
        )
    if counters is not None:
        (run / f"run_stats_{name[4:]}.json").write_text(
            json.dumps({"timestamp": name[4:], "full_text": counters}), encoding="utf-8"
        )
    return run


@pytest.fixture
def env(tmp_path):
    """Patch the four seams the tools read the world through."""

    def build(store=None, run_dir=None, papers=None, cfg=None, fetcher=None):
        store = store if store is not None else FakeStore()
        papers = papers if papers is not None else []
        hunter = MagicMock()
        hunter.config.fulltext_config.return_value = {
            "enabled": False,
            "email": "me@example.com",
            "max_papers": 200,
            "time_budget_seconds": 900,
            **(cfg or {}),
        }
        hunter.full_text_fetcher = fetcher or (lambda doi: ExtractedDocument(text=LONG_TEXT))

        patches = [
            patch.object(ft, "_get_vector_store", return_value=store),
            patch.object(ft, "_latest_run_dir", return_value=run_dir),
            patch.object(ft, "_load_latest_papers", return_value=papers),
            patch.object(ft, "_make_hunter", return_value=hunter),
        ]
        for p in patches:
            p.start()
        return store, hunter

    yield build
    patch.stopall()


def hit(parent_id, relevance, title="", section="method", index=0, text="passage"):
    return {
        "chunk_id": f"{parent_id}::{index}",
        "parent_id": parent_id,
        "section": section,
        "index": index,
        "start": index * 100,
        "end": index * 100 + 90,
        "title": title,
        "doi": "",
        "year": "",
        "source": "EuropePmcSource",
        "text": text,
        "relevance": relevance,
    }


# ── fulltext_status ─────────────────────────────────────────────────────────


async def test_status_reports_the_counters_of_the_last_run(tmp_path, mock_ctx, env):
    run = make_run(
        tmp_path,
        statuses=["obtained", "obtained", "no_open_access"],
        counters={"obtained": 2, "no_open_access": 1, "already_indexed": 5},
    )
    env(store=FakeStore(count=273), run_dir=run)

    result = await ft.fulltext_status(mock_ctx)

    assert "obtained: 2" in result
    assert "no_open_access: 1" in result
    assert "already_indexed: 5" in result
    assert "273" in result


async def test_status_says_the_step_did_not_run_instead_of_reporting_zero(
    tmp_path, mock_ctx, env
):
    """An absent column is not a measurement of zero."""
    run = make_run(tmp_path, statuses=None, counters=None)
    env(run_dir=run)

    result = await ft.fulltext_status(mock_ctx)

    assert "did not run" in result
    assert "0 obtained" not in result
    assert "obtained: 0" not in result


async def test_status_labels_the_chunk_count_as_persistent(tmp_path, mock_ctx, env):
    """Chunks outlive the run: presenting them as this run's result would lie."""
    run = make_run(tmp_path, statuses=["no_open_access"], counters={"no_open_access": 1})
    env(store=FakeStore(count=42), run_dir=run)

    result = await ft.fulltext_status(mock_ctx)

    assert "persistent" in result


async def test_status_works_with_no_run_at_all(mock_ctx, env):
    env(run_dir=None)

    result = await ft.fulltext_status(mock_ctx)

    assert "No run found" in result
    assert "index_fulltext" in result


async def test_status_names_the_missing_pdf_extra(mock_ctx, env):
    """Without pypdf half the chain is off, and that must not look like 'no OA'."""
    env()
    with patch.object(ft, "_pypdf_installed", return_value=False):
        result = await ft.fulltext_status(mock_ctx)

    assert "pypdf" in result
    assert "fulltext" in result, "the message must say which extra to install"


# ── index_fulltext ──────────────────────────────────────────────────────────


async def test_index_fulltext_reports_the_counters(mock_ctx, env):
    papers = [{"Title": "One", "DOI": "10.1/a"}, {"Title": "Two", "DOI": ""}]
    store = FakeStore()
    env(store=store, papers=papers)

    result = await ft.index_fulltext(ctx=mock_ctx)

    assert "obtained: 1" in result
    assert "no_doi: 1" in result
    assert len(store.indexed) == 1


async def test_index_fulltext_forwards_the_limit(mock_ctx, env):
    papers = [{"Title": f"P{i}", "DOI": f"10.1/{i}"} for i in range(4)]
    env(papers=papers)

    result = await ft.index_fulltext(limit=1, ctx=mock_ctx)

    assert "obtained: 1" in result
    assert "not_attempted: 3" in result


async def test_index_fulltext_forwards_force(mock_ctx, env):
    from academic_hunter.core.evaluation.qrels import doc_id_for

    parent_id = doc_id_for("One", "10.1/a")
    store = FakeStore(already={parent_id})
    env(store=store, papers=[{"Title": "One", "DOI": "10.1/a"}])

    skipped = await ft.index_fulltext(ctx=mock_ctx)
    assert "already_indexed: 1" in skipped
    assert store.deleted == []

    forced = await ft.index_fulltext(force=True, ctx=mock_ctx)
    assert "obtained: 1" in forced
    assert store.deleted == [parent_id]


async def test_index_fulltext_says_so_when_the_store_cannot_hold_chunks(mock_ctx, env):
    class NotAChunkStore:
        pass

    env(store=NotAChunkStore(), papers=[{"Title": "One", "DOI": "10.1/a"}])

    result = await ft.index_fulltext(ctx=mock_ctx)

    assert "cannot hold chunks" in result


async def test_index_fulltext_without_papers_points_at_run_search(mock_ctx, env):
    env(papers=[])

    result = await ft.index_fulltext(ctx=mock_ctx)

    assert "run_search" in result


async def test_index_fulltext_does_not_spend_a_request_on_a_paper_without_a_doi(
    mock_ctx, env
):
    calls = []

    def fetcher(doi):
        calls.append(doi)
        raise NoOpenAccessVersion(doi)

    env(papers=[{"Title": "No doi", "DOI": ""}], fetcher=fetcher)

    await ft.index_fulltext(ctx=mock_ctx)

    assert calls == []


# ── chunk_search ────────────────────────────────────────────────────────────


async def test_chunk_search_groups_hits_under_their_paper(mock_ctx, env):
    # Deliberately out of order: the weaker paper comes first, so grouping has
    # to sort rather than preserve whatever the store returned.
    store = FakeStore(hits=[
        hit("doi:10.1/b", 0.55, title="Another paper", index=0),
        hit("doi:10.1/a", 0.72, title="Ledgers in practice", index=1, section="results"),
        hit("doi:10.1/a", 0.91, title="Ledgers in practice", index=0),
    ])
    env(store=store)

    result = await ft.chunk_search("latency", top_k=2, ctx=mock_ctx)

    assert result.index("Ledgers in practice") < result.index("Another paper")
    assert "results" in result, "the second chunk of the same paper is missing"
    # 2 papers claimed, so the search must ask for more than 2 chunks: they come
    # grouped, and 10 chunks can easily be 2 papers.
    assert store.queries[0][1] > 2


async def test_chunk_search_caps_the_chunks_per_paper(mock_ctx, env):
    store = FakeStore(hits=[hit("doi:10.1/a", 0.9, title="Paper", index=i) for i in range(5)])
    env(store=store)

    result = await ft.chunk_search("latency", top_k=1, per_paper=2, ctx=mock_ctx)

    assert result.count("chunk ") == 2


async def test_chunk_search_reports_section_and_offsets_and_no_page(mock_ctx, env):
    """There is no page number to report: PDF has pages, the JATS source has none.

    A `page` field would be present for one source and absent for the other,
    which is worse than not having it. The offsets locate the passage in the
    extracted text instead.
    """
    env(store=FakeStore(hits=[hit("doi:10.1/a", 0.9, title="Paper", index=3)]))

    result = await ft.chunk_search("latency", ctx=mock_ctx)

    assert "method" in result
    assert "chars 300–390" in result
    # "passage" is not the word under test here — a page marker would be a
    # number attached to a page, and there is no such number to attach.
    assert "page" not in result.lower().replace("passage", "")


async def test_chunk_search_falls_back_to_the_run_dataset_for_the_title(mock_ctx, env):
    """Chunks indexed before the identity existed carry no title."""
    from academic_hunter.core.evaluation.qrels import doc_id_for

    parent_id = doc_id_for("A study of ledgers", "10.1/a")
    env(
        store=FakeStore(hits=[hit(parent_id, 0.9, title="")]),
        papers=[{"Title": "A study of ledgers", "DOI": "10.1/a"}],
    )

    result = await ft.chunk_search("latency", ctx=mock_ctx)

    assert "A study of ledgers" in result


async def test_chunk_search_without_a_title_says_the_id_is_an_id(mock_ctx, env):
    env(store=FakeStore(hits=[hit("doi:10.1/a", 0.9, title="")]), papers=[])

    result = await ft.chunk_search("latency", ctx=mock_ctx)

    assert "doi:10.1/a" in result
    assert "derived id" in result


async def test_chunk_search_on_an_empty_collection_points_at_the_indexer(mock_ctx, env):
    env(store=FakeStore(hits=[]))

    result = await ft.chunk_search("latency", ctx=mock_ctx)

    assert "index_fulltext" in result


async def test_chunk_search_reaches_the_collection_it_is_given(mock_ctx, env):
    store = FakeStore(hits=[hit("doi:10.1/a", 0.9, title="Paper")])
    env(store=store)

    await ft.chunk_search("latency", collection_name="paper_chunks_eval", ctx=mock_ctx)

    assert store.queries[0][2] == "paper_chunks_eval"
