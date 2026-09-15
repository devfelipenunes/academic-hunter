"""A similaridade reportada tem de ser a que o índice mede.

Deliberadamente contra um ChromaDB real: a métrica é uma propriedade da coleção, e
um mock devolveria o que o teste mandasse.
"""

import numpy as np
import pytest

chromadb = pytest.importorskip("chromadb")

from academic_hunter.plugins.vector_stores.chroma import ChromaVectorStore

PAPERS = [
    {"Title": "Blockchain latency in payment rails", "Abstract": "Blockchain consensus latency."},
    {"Title": "A study of ledgers", "Abstract": "Distributed ledger throughput."},
    {"Title": "Marine biology of coral reefs", "Abstract": "Coral reef ecology."},
]

QUERY = "blockchain payment latency"


@pytest.fixture
def store(tmp_path):
    return ChromaVectorStore(db_dir=str(tmp_path / "chroma"))


def _cosine_by_title(store, query):
    """The true cosine, computed with the very embedder the index used."""
    collection = store.client.get_collection("papers")
    embed = collection._embedding_function
    q = np.array(embed([query])[0])
    documents = [f"{p['Title']}\n\n{p['Abstract']}" for p in PAPERS]
    matrix = np.array(embed(documents))
    cosines = (matrix @ q) / (np.linalg.norm(matrix, axis=1) * np.linalg.norm(q))

    return {
        f"{p['Title']}\n\n{p['Abstract']}": float(c) for p, c in zip(PAPERS, cosines)
    }


def test_the_reported_relevance_is_the_cosine_similarity(store):
    """The collection was created without declaring a metric, so Chroma used
    squared L2 — and the code converted with `(1.414 - distance) / 1.414`.

    That is neither the cosine nor a rescaling of it. Measured: a paper at cosine
    0.4526 came back as 0.2257, and the error grows as the paper gets less
    relevant, so `score_threshold` means something different at every point of
    the scale.
    """
    store.index_papers([dict(p) for p in PAPERS])

    results = store.query(QUERY, top_k=3)
    expected = _cosine_by_title(store, QUERY)

    assert len(results) == len(PAPERS)
    for row in results:
        assert row["semantic_relevance"] == pytest.approx(
            expected[row["abstract_preview"]], abs=0.01
        ), f"{row['title']}: reported {row['semantic_relevance']}"


def test_the_order_is_the_similarity_order(store):
    store.index_papers([dict(p) for p in PAPERS])

    reported = [row["semantic_relevance"] for row in store.query(QUERY, top_k=3)]

    assert reported == sorted(reported, reverse=True)


def test_a_threshold_selects_the_same_papers_the_cosine_would(store):
    """`score_threshold` is compared against the reported number, so a
    compressed scale silently drops papers that pass the cosine."""
    store.index_papers([dict(p) for p in PAPERS])
    expected = _cosine_by_title(store, QUERY)

    passing = {
        row["title"] for row in store.query(QUERY, top_k=3, score_threshold=0.4)
    }
    should_pass = {
        p["Title"] for p in PAPERS if expected[f"{p['Title']}\n\n{p['Abstract']}"] >= 0.4
    }

    assert passing == should_pass
