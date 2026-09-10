"""Chunk retrieval against a real ChromaDB instance.

Deliberately not mocked: the `where` filter and the metadata round-trip are
exactly what a mock cannot check, and they are what the chunk→paper projection
depends on.
"""

import pytest

from academic_hunter.core.ports.vector_store import ChunkStorePort

chromadb = pytest.importorskip("chromadb")

from academic_hunter.plugins.vector_stores.chroma import ChromaVectorStore


@pytest.fixture
def store(tmp_path):
    return ChromaVectorStore(db_dir=str(tmp_path / "chroma"))


def chunk(chunk_id, parent_id, text, section="method", index=0):
    return {
        "chunk_id": chunk_id,
        "parent_id": parent_id,
        "text": text,
        "section": section,
        "index": index,
        "start": index * 100,
        "end": index * 100 + 90,
    }


def test_the_store_satisfies_the_chunk_port(store):
    """The pipeline asks with `isinstance`, so structural match is the contract."""
    assert isinstance(store, ChunkStorePort)


def test_chunks_round_trip_with_their_metadata(store):
    records = [
        chunk("doi:10.1/a::0", "doi:10.1/a", "latency in distributed ledgers"),
        chunk("doi:10.1/b::0", "doi:10.1/b", "a different subject entirely", section="abstract"),
    ]

    assert store.index_chunks(records) is True

    hits = store.query_chunks("latency in distributed ledgers", top_k=2)
    assert hits, "nothing came back"
    top = hits[0]
    assert top["parent_id"] == "doi:10.1/a"
    assert top["section"] == "method"
    assert top["start"] == 0
    assert top["end"] == 90
    assert "latency" in top["text"]


def test_has_and_delete_chunks_are_scoped_to_the_parent(store):
    store.index_chunks([
        chunk("doi:10.1/a::0", "doi:10.1/a", "first"),
        chunk("doi:10.1/a::1", "doi:10.1/a", "second", index=1),
        chunk("doi:10.1/b::0", "doi:10.1/b", "other paper"),
    ])

    assert store.has_chunks("doi:10.1/a") is True
    assert store.has_chunks("doi:10.1/missing") is False

    assert store.delete_chunks("doi:10.1/a") == 2
    assert store.has_chunks("doi:10.1/a") is False
    assert store.has_chunks("doi:10.1/b") is True, "deleted someone else's chunks"


def test_indexing_chunks_leaves_the_papers_collection_alone(store):
    """The whole reason for a separate collection: no regression to the corpus."""
    store.index_papers([{"Title": "A paper", "Abstract": "About ledgers.", "DOI": "10.1/a"}])
    before = store.collection_stats("papers")["count"]

    store.index_chunks([chunk("doi:10.1/a::0", "doi:10.1/a", "a fragment")])

    assert store.collection_stats("papers")["count"] == before
    assert "paper_chunks" in store.list_collections()


def test_an_empty_batch_is_not_an_error(store):
    assert store.index_chunks([]) is True


def test_querying_a_collection_that_does_not_exist_returns_nothing(store):
    assert store.query_chunks("anything") == []


def test_has_chunks_on_a_missing_collection_is_false(store):
    assert store.has_chunks("doi:10.1/a") is False


def test_deleting_from_a_missing_collection_returns_zero(store):
    assert store.delete_chunks("doi:10.1/a") == 0
