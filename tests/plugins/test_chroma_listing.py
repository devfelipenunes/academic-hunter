"""Ler a coleção inteira, e não o que estiver perto de uma frase.

As análises de corpus consultavam `store.query("research topic analysis", top_k=1000)`.
O Chroma limita ao tamanho da coleção, mas isso só vale quando o limite **alcança**
a coleção: com mais documentos que isso, o resultado são os mais próximos da
frase, não o corpus — e agrupamento, tendências e duplicatas passam a descrever
uma vizinhança semântica de "research topic analysis".
"""

import pytest

chromadb = pytest.importorskip("chromadb")

from academic_hunter.plugins.vector_stores.chroma import ChromaVectorStore

TOPICS = [
    "Blockchain consensus latency",
    "Coral reef bleaching",
    "Byzantine fault tolerance",
    "Migratory patterns of terns",
    "Zero knowledge proofs",
]


@pytest.fixture
def store(tmp_path):
    made = ChromaVectorStore(db_dir=str(tmp_path / "chroma"))
    made.index_papers([
        {"Title": title, "Abstract": f"About {title.lower()}."} for title in TOPICS
    ])
    return made


def test_every_indexed_paper_is_returned(store):
    """Not the ones nearest a phrase: the collection."""
    papers = store.all_papers()

    assert {p["title"] for p in papers} == set(TOPICS)


def test_the_phrase_would_have_left_some_out(store):
    """The defect this replaces, demonstrated.

    A query ranks by similarity to the phrase, so the papers least like
    "research topic analysis" are the ones that fall off the end — here, the ones
    that have nothing to do with research methodology.
    """
    nearest = {p["title"] for p in store.query("research topic analysis", top_k=2)}

    assert nearest != set(TOPICS), "the point of the test is that a query samples"


def test_the_listing_carries_what_the_analyses_read(store):
    """Clustering wants the abstract, trending the year, dedup the doi."""
    paper = next(p for p in store.all_papers() if p["title"] == TOPICS[0])

    assert paper["abstract"] == "About blockchain consensus latency."
    assert "doi" in paper and "year" in paper and "source" in paper


def test_a_listing_of_an_empty_collection_is_empty(tmp_path):
    empty = ChromaVectorStore(db_dir=str(tmp_path / "nothing"))

    assert empty.all_papers() == []


# ── o que as análises usam ──────────────────────────────────────────────────


def test_the_corpus_is_read_rather_than_searched():
    """A query answers which documents sit nearest a phrase.

    An analysis of the corpus needs the corpus, and the two are different
    questions — asking the first and reporting the second is how clustering came
    to describe a neighbourhood of "research topic analysis".
    """
    from academic_hunter.interfaces.mcp.tools._utils import corpus_of

    class Listing:
        def __init__(self):
            self.listed = False

        def all_papers(self, collection_name="papers"):
            self.listed = True
            return [{"title": "Every paper"}]

        def query(self, prompt, top_k=5):
            raise AssertionError("the collection was searched instead of read")

    store = Listing()

    assert corpus_of(store, 1000) == [{"title": "Every paper"}]
    assert store.listed


def test_a_store_that_cannot_list_says_what_it_is_doing():
    """Falling back to a query is a sample, and the log says so."""
    from academic_hunter.interfaces.mcp.tools._utils import corpus_of

    class QueryOnly:
        def query(self, prompt, top_k=5):
            return [{"title": f"near {prompt}"}]

    assert corpus_of(QueryOnly(), 10) == [{"title": "near research paper"}]
