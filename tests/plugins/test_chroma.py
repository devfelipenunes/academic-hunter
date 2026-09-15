"""Tests for ChromaVectorStore."""
import pytest
from unittest.mock import patch, MagicMock
from academic_hunter.plugins.vector_stores.chroma import ChromaVectorStore


@pytest.fixture
def store():
    s = ChromaVectorStore(db_dir="/tmp/test_chroma")
    # Mock the client and collection to avoid real ChromaDB
    s._client = MagicMock()
    s._collection = MagicMock()
    return s


def test_list_collections_returns_names(store):
    """list_collections returns collection names."""
    mock_coll1 = MagicMock()
    mock_coll1.name = "papers"
    mock_coll2 = MagicMock()
    mock_coll2.name = "backup"
    store.client.list_collections.return_value = [mock_coll1, mock_coll2]
    assert store.list_collections() == ["papers", "backup"]


def test_list_collections_error(store):
    """list_collections returns empty list on error."""
    store.client.list_collections.side_effect = Exception("ChromaDB error")
    assert store.list_collections() == []


def test_collection_stats_exists(store):
    """collection_stats returns stats for existing collection."""
    mock_coll = MagicMock()
    mock_coll.count.return_value = 42
    mock_coll.metadata = {"created": "2025-01-01"}
    store.client.get_collection.return_value = mock_coll
    stats = store.collection_stats("papers")
    assert stats["name"] == "papers"
    assert stats["count"] == 42
    assert stats["metadata"]["created"] == "2025-01-01"


def test_collection_stats_not_found(store):
    """collection_stats returns empty stats when collection doesn't exist."""
    store.client.get_collection.side_effect = Exception("Not found")
    stats = store.collection_stats("nonexistent")
    assert stats["count"] == 0
    assert stats["status"] == "empty"


def test_collection_stats_error(store):
    """collection_stats handles non-get_collection errors."""
    store.client.get_collection.side_effect = Exception("Get failed")
    stats = store.collection_stats("broken")
    assert stats["count"] == 0


def test_delete_collection_success(store):
    """delete_collection returns True on success."""
    assert store.delete_collection("papers") is True
    store.client.delete_collection.assert_called_with("papers")


def test_delete_collection_error(store):
    """delete_collection returns False on error."""
    store.client.delete_collection.side_effect = Exception("Delete failed")
    assert store.delete_collection("papers") is False


def test_index_papers_empty(store):
    """index_papers returns True when no papers."""
    assert store.index_papers([]) is True


def test_index_papers_success(store):
    """index_papers indexes papers and returns True."""
    mock_coll = MagicMock()
    store.client.get_collection.return_value = mock_coll

    papers = [
        {"Title": "Paper One", "DOI": "10.1000/one", "Abstract": "Abstract one."},
        {"Title": "Paper Two", "Abstract": "Abstract two."},
    ]
    assert store.index_papers(papers) is True
    assert mock_coll.upsert.called


def test_index_papers_empty_text_skipped(store):
    """index_papers skips papers with no text content."""
    mock_coll = MagicMock()
    store.client.get_collection.return_value = mock_coll

    papers = [
        {"Title": "", "Abstract": ""},
        {"Title": "Valid Paper", "Abstract": "Has content."},
    ]
    assert store.index_papers(papers) is True
    # Only the valid paper should be upserted
    call_args = mock_coll.upsert.call_args
    assert call_args is not None
    assert len(call_args.kwargs.get("documents", [])) == 1


def test_index_papers_failure(store):
    """index_papers returns False on error."""
    store.client.get_collection.side_effect = Exception("ChromaDB error")
    store.client.create_collection.side_effect = Exception("Create also fails")
    papers = [{"Title": "Paper", "Abstract": "Abstract."}]
    assert store.index_papers(papers) is False


def test_query_empty_collection(store):
    """query returns empty list when collection doesn't exist."""
    store.client.get_collection.side_effect = Exception("Not found")
    assert store.query("test", top_k=5) == []


def test_query_zero_count(store):
    """query returns empty list when collection has zero documents."""
    mock_coll = MagicMock()
    mock_coll.count.return_value = 0
    store.client.get_collection.return_value = mock_coll
    assert store.query("test", top_k=5) == []


def test_query_returns_results(store):
    """query returns parsed results from ChromaDB."""
    mock_coll = MagicMock()
    mock_coll.count.return_value = 10
    mock_coll.configuration = {"hnsw": {"space": "l2"}}
    store.client.get_collection.return_value = mock_coll

    mock_coll.query.return_value = {
        "ids": [["id1", "id2"]],
        "metadatas": [[
            {"title": "Paper 1", "doi": "10.1000/1", "year": "2024"},
            {"title": "Paper 2", "doi": "10.1000/2", "year": "2023"},
        ]],
        "distances": [[0.5, 0.8]],
        "documents": [["Doc 1 content.", "Doc 2 content."]],
    }
    results = store.query("test query", top_k=5)
    assert len(results) == 2
    assert results[0]["title"] == "Paper 1"
    assert results[0]["doi"] == "10.1000/1"
    # Chroma's `l2` distance is the *squared* one, and the embedded vectors are
    # unit length, so `cos = 1 - d/2`. Collections that predate the declared
    # metric still report `l2`, and this is the branch they take.
    assert results[0]["semantic_relevance"] == pytest.approx(0.75, rel=0.01)
    assert results[1]["semantic_relevance"] == pytest.approx(0.6, rel=0.01)


def test_a_cosine_collection_converts_with_its_own_formula(store):
    """`cosine` distance already is `1 - cos`, so it is not halved."""
    mock_coll = MagicMock()
    mock_coll.count.return_value = 1
    mock_coll.configuration = {"hnsw": {"space": "cosine"}}
    mock_coll.query.return_value = {
        "ids": [["id1"]],
        "metadatas": [[{"title": "Paper 1"}]],
        "distances": [[0.25]],
        "documents": [["Doc 1."]],
    }
    store.client.get_collection.return_value = mock_coll

    results = store.query("q", top_k=1)

    assert results[0]["semantic_relevance"] == pytest.approx(0.75, rel=0.01)


def test_query_with_score_threshold(store):
    """query filters results below score_threshold."""
    mock_coll = MagicMock()
    mock_coll.count.return_value = 10
    mock_coll.configuration = {"hnsw": {"space": "l2"}}
    store.client.get_collection.return_value = mock_coll

    mock_coll.query.return_value = {
        "ids": [["id1", "id2"]],
        "metadatas": [[{"title": "Paper 1"}, {"title": "Paper 2"}]],
        "distances": [[0.2, 1.2]],
        "documents": [["Content 1", "Content 2"]],
    }
    # `l2`, so cos = 1 - d/2: 0.2 → 0.9, and 1.2 → 0.4, under the threshold.
    results = store.query("test", top_k=5, score_threshold=0.5)
    assert len(results) == 1
    assert results[0]["title"] == "Paper 1"


def test_query_error(store):
    """query returns empty list on unexpected error."""
    store.client.get_collection.side_effect = Exception("Unexpected")
    assert store.query("test") == []


def test_get_or_create_collection_creates(store):
    """Creates collection when get fails."""
    store.client.get_collection.side_effect = Exception("Not found")
    s = ChromaVectorStore(db_dir="/tmp/test_chroma")
    s._client = store.client
    coll = s._get_or_create_collection("new_coll")
    assert coll is not None
    store.client.create_collection.assert_called_once()


def test_a_query_result_carries_a_key_named_abstract(tmp_path):
    """The producer's key, not the consumers'.

    Two readers build text from `paper["abstract"]`: `novelty` embeds
    `title + abstract` for its outlier detection, and `paper_context` prints it.
    The store returned `abstract_preview` and no `abstract`, so novelty ran its
    analysis on titles alone and the context never showed an abstract — and
    neither failed, because a missing dict key is not an error.
    """
    store = ChromaVectorStore(db_dir=str(tmp_path / "chroma"))
    store.index_papers([
        {"Title": "Ledgers at scale", "Abstract": "We measure ledger throughput."}
    ])

    result = store.query("ledger throughput", top_k=1)[0]

    assert result["abstract"] == "We measure ledger throughput."
    assert result["abstract_preview"], "the preview is kept for display"
