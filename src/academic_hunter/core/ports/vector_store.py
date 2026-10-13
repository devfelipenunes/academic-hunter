"""Vector store port: native RAG capabilities behind an interface.

The pipeline receives a factory for this, so the concrete store (ChromaDB,
LanceDB, FAISS) is chosen at the composition root rather than imported by core.
"""

import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Protocol, Sequence, runtime_checkable

LEGACY_COLLECTION = "papers"
"""The collection every run indexed into before a review could name its own.

Kept as the fallback so an installation that predates ``settings.collection_name``
keeps reading the papers it already has, and so a store built without a review in
hand still works.
"""


_CHROMA_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{1,61}[a-zA-Z0-9]$")
"""ChromaDB's own rule for a collection name.

Spelled out rather than tested with ``str.isalnum``, which is true for ``é``:
``"reviewé"`` would pass here and be refused at the first write, after the
search has already been paid for.
"""


def is_valid_collection_name(name: str) -> bool:
    """Whether ChromaDB will accept ``name`` as a collection name.

    3-63 characters, ASCII alphanumerics plus ``_``, ``-`` and ``.``, an
    alphanumeric at each end, and no ``..`` anywhere. A name that fails this is
    rejected at the first write, which is after the search has already run.
    """
    if not isinstance(name, str) or ".." in name:
        return False
    return _CHROMA_NAME.match(name) is not None


def review_collection_name(topic: str = "", anchors: Optional[Dict[str, Any]] = None) -> str:
    """A ChromaDB-legal collection name for one review, or ``""``.

    One collection per review, because one collection for every review is what
    this replaces: two searches leave 1040 papers in a single ``papers``
    collection, and clustering, trends and duplicate detection then describe both
    of them while reading as though they described the current one.

    Derived from the ``topic`` that ``update_config`` already takes, so the runs
    that revise a review keep writing to the same collection; the anchors are the
    fallback for an update that names no topic. Returning ``""`` rather than a
    guess is deliberate: the caller can then leave an existing name alone instead
    of silently moving a corpus.
    """
    source = str(topic or "").strip()
    if not source and anchors:
        source = " ".join(
            str(term) for terms in anchors.values() for term in (terms or [])
        )

    slug = re.sub(r"[^a-z0-9]+", "_", source.lower()).strip("_")
    slug = re.sub(r"_+", "_", slug)
    if not slug:
        return ""

    name = f"review_{slug}"[:63].strip("_-")
    return name if is_valid_collection_name(name) else ""


class BaseVectorStore(ABC):
    """
    Abstract Base Class for integrating Native RAG capabilities.
    Any new Vector DB (ChromaDB, LanceDB, FAISS) must implement this interface.
    """

    @abstractmethod
    def index_papers(self, papers: List[Dict[str, Any]]) -> bool:
        """
        Convert paper metadata/abstracts into vector embeddings and index them.

        Args:
            papers: A list of paper dictionaries.

        Returns:
            bool: True if indexing was successful.
        """
        pass

    @abstractmethod
    def query(self, prompt: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Perform a semantic similarity search against the vector database.

        Args:
            prompt: The user's query string.
            top_k: Number of results to return.

        Returns:
            List[Dict[str, Any]]: A list of semantically relevant papers.
        """
        pass


@runtime_checkable
class PaperListingPort(Protocol):
    """Reading the collection, as opposed to searching it.

    The analyses of a corpus — clustering, trends, duplicates — describe the
    corpus, and a query answers a different question: the documents nearest a
    phrase. Asking with a phrase made those results depend on how close each
    paper sits to "research topic analysis".

    Separate from :class:`BaseVectorStore` for the reason given below: a store
    that cannot list is still a valid vector store, and callers degrade.
    """

    def all_papers(self, collection_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Every indexed paper, in no particular order, with no similarity.

        ``None`` means the collection the store was built for — the review in
        hand — rather than a hardcoded name, which is what made every analysis
        describe whichever reviews happened to share the one collection.
        """
        ...


@runtime_checkable
class ChunkStorePort(Protocol):
    """Retrieval over document *fragments* rather than whole papers.

    Deliberately not folded into :class:`BaseVectorStore`. Adding these four
    methods there would make every existing store — including the mocks — fail to
    satisfy the contract, and a store that cannot do chunk retrieval is still a
    perfectly valid vector store. Callers ask with ``isinstance(store,
    ChunkStorePort)`` and degrade when the answer is no.
    """

    def index_chunks(
        self, chunks: Sequence[Dict[str, Any]], collection_name: str = "paper_chunks"
    ) -> bool:
        """Embed and store chunk records. Returns True on success."""
        ...

    def query_chunks(
        self, prompt: str, top_k: int = 10, collection_name: str = "paper_chunks"
    ) -> List[Dict[str, Any]]:
        """Return the chunks most similar to ``prompt``, with their metadata."""
        ...

    def has_chunks(self, parent_id: str, collection_name: str = "paper_chunks") -> bool:
        """Whether any chunk belonging to ``parent_id`` is already indexed."""
        ...

    def delete_chunks(
        self,
        parent_id: str,
        collection_name: str = "paper_chunks",
        *,
        keep_ids: Sequence[str] = (),
    ) -> int:
        """Remove the chunks of ``parent_id`` that are not in ``keep_ids``.

        Returns how many were removed. ``keep_ids`` is what makes a reindex safe:
        the caller indexes the replacement first and then names what it kept, so
        the store never has to guess which chunks belong to the older version.
        """
        ...
