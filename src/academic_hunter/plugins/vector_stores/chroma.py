"""ChromaDB vector store for RAG on academic papers.

Uses ONNX-based all-MiniLM-L6-v2 embeddings via ChromaDB's DefaultEmbeddingFunction.
"""

import hashlib
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from .base import BaseVectorStore

logger = logging.getLogger("academic_hunter.vector_store")


def _as_float(value: Any, default: float = 0.0) -> float:
    """Coerce a metadata value to float.

    ``paper.get("score", 0.0)`` only defaults when the *key* is missing; a key
    that is present and null returns ``None`` and ``float(None)`` raises. The
    upsert is one batch, so a single such value discards the whole index.
    """
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return default if result != result else result  # NaN != NaN


def _as_int(value: Any, default: int = 0) -> int:
    """Coerce a metadata value to int; see :func:`_as_float`."""
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _as_str(value: Any) -> str:
    """Coerce to str, mapping a missing value to "" rather than "None"."""
    return "" if value is None else str(value)


def _result_row(doc_id: str, metadata: dict, document: str) -> Dict[str, Any]:
    """One paper as the tools receive it, without any similarity.

    Shared by `query` and `all_papers` so the two cannot drift into returning
    different shapes for the same document.
    """
    metadata = metadata or {}
    document = document or ""
    title = metadata.get("title") or (document.split("\n")[0] if document else doc_id)

    return {
        "id": doc_id,
        "title": title,
        "doi": metadata.get("doi", ""),
        "year": metadata.get("year", ""),
        "source": metadata.get("source", ""),
        "score": metadata.get("score", 0.0),
        "citations": metadata.get("citations", 0),
        "venue": metadata.get("venue", ""),
        "url": metadata.get("url", ""),
        "abstract": _abstract_of(metadata, document, title),
        "abstract_preview": document[:500],
    }


def _abstract_of(metadata: dict, document: str, title: str) -> str:
    """The abstract, from the metadata or derived from the indexed document.

    Collections built before the field existed hold only ``title\\n\\nabstract``
    as one string, truncated at the preview boundary — derived is worse than
    stored, and better than the nothing those collections reported.
    """
    stored = metadata.get("abstract")
    if stored:
        return str(stored)

    separator = f"{title}\n\n"
    if title and document.startswith(separator):
        return document[len(separator):]
    return document


def _space_of(collection) -> str:
    """The metric the collection actually uses.

    `hnsw:space` lives in the collection's configuration, and collections created
    before it was declared report `l2` — Chroma's default — even though their
    metadata says nothing about it.
    """
    space = None
    try:
        space = collection.configuration["hnsw"]["space"]
    except Exception:
        pass
    if space is None:
        space = (collection.metadata or {}).get("hnsw:space")

    # An unrecognised value falls back to the default rather than through the
    # `else` of the conversion, where a typo would silently mean "l2".
    normalised = str(space).lower() if space is not None else ""
    return normalised if normalised in ("l2", "cosine", "ip") else "l2"


def _cosine_from(distance: float, space: str) -> float:
    """Chroma's distance as a cosine similarity, clamped to [0, 1].

    The formula depends on the space, and getting it wrong is not a cosmetic
    error: `cosine` returns ``1 - cos``, while `l2` returns the **squared**
    Euclidean distance, which for the unit vectors this store embeds is
    ``2 - 2·cos``. The ``(1.414 - d) / 1.414`` this replaced was neither, and it
    compressed the scale — a paper at 0.45 came back as 0.23, under the
    thresholds callers filter by.
    """
    if space == "cosine":
        similarity = 1.0 - distance
    elif space == "ip":
        # Inner product. On the unit vectors embedded here that is the cosine.
        similarity = 1.0 - distance
    else:
        similarity = 1.0 - distance / 2.0
    return max(0.0, min(1.0, similarity))


class ChromaVectorStore(BaseVectorStore):
    """ChromaDB-backed vector store for semantic paper search."""

    def __init__(self, db_dir: str = ".academic_hunter/chroma_db"):
        self.db_dir = db_dir
        self._client = None
        self._collection = None

    @property
    def client(self):
        """Lazy-init ChromaDB PersistentClient."""
        if self._client is None:
            import chromadb
            os.makedirs(self.db_dir, exist_ok=True)
            self._client = chromadb.PersistentClient(path=self.db_dir)
        return self._client

    def _get_or_create_collection(self, name: str = "papers"):
        """Get or create a collection by name, with error handling for existing."""
        try:
            return self.client.get_collection(name)
        except Exception:
            # ChromaDB raises NotFoundError (or ValueError in older versions)
            return self.client.create_collection(
                name,
                metadata={
                    "created": datetime.now().isoformat(),
                    "type": "academic_papers",
                    # Declared rather than inherited: Chroma's default is squared
                    # L2, and the conversion back to a similarity depends on
                    # knowing which one it was. Collections built before this
                    # keep working — `_cosine_from` reads what the collection
                    # actually uses.
                    "hnsw:space": "cosine",
                },
            )

    def index_papers(self, papers: List[Dict[str, Any]], collection_name: str = "papers") -> bool:
        """
        Convert paper metadata/abstracts into vector embeddings and index them.

        Args:
            papers: A list of paper dictionaries (from consolidated_results).
            collection_name: ChromaDB collection to use.

        Returns:
            bool: True if indexing was successful.
        """
        if not papers:
            logger.warning("No papers to index.")
            return True

        try:
            collection = self._get_or_create_collection(collection_name)

            documents = []
            metadatas = []
            ids = []

            for paper in papers:
                title = paper.get("Title", "") or ""
                abstract = paper.get("Abstract", "") or ""
                doi = paper.get("DOI", "") or ""

                doc_text = f"{title}\n\n{abstract}" if abstract else title
                if not doc_text.strip():
                    continue

                title_hash = hashlib.md5(title.encode()).hexdigest()[:12] if title else ""
                doc_id = doi or title_hash or f"paper_{len(ids)}"

                documents.append(doc_text)
                metadatas.append({
                    "title": title[:500],
                    # Consumers build their text from `title` + `abstract`:
                    # `novelty` embeds the pair for its outlier detection, and
                    # `paper_context` prints it. Stored as its own field so those
                    # two read what they say they read.
                    "abstract": abstract,
                    "doi": doi,
                    "year": _as_str(paper.get("Year")),
                    "source": _as_str(paper.get("Source")),
                    "score": _as_float(paper.get("Relevance_Score")),
                    "citations": _as_int(paper.get("Citations")),
                    "venue": _as_str(paper.get("Venue")),
                    "anchor_category": _as_str(paper.get("Anchor_Category")),
                    "tech_category": _as_str(paper.get("Tech_Category")),
                    "url": _as_str(paper.get("URL")),
                })
                ids.append(doc_id)

            if not documents:
                logger.warning("No valid documents to index after filtering.")
                return True

            collection.upsert(documents=documents, metadatas=metadatas, ids=ids)
            logger.info(f"Indexed {len(documents)} papers into ChromaDB collection '{collection_name}'.")
            return True

        except Exception as e:
            logger.error(f"ChromaDB indexing failed: {e}")
            return False

    def query(
        self, prompt: str, top_k: int = 5, collection_name: str = "papers",
        score_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Semantic similarity search against indexed papers."""
        try:
            try:
                collection = self.client.get_collection(collection_name)
            except Exception:
                logger.warning(f"Collection '{collection_name}' does not exist yet.")
                return []

            count = collection.count()
            if count == 0:
                logger.warning(f"Collection '{collection_name}' is empty.")
                return []

            results = collection.query(
                query_texts=[prompt],
                n_results=min(top_k, count),
                include=["documents", "metadatas", "distances"],
            )

            papers = []
            if results["ids"] and results["ids"][0]:
                for i, doc_id in enumerate(results["ids"][0]):
                    metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                    distance = results["distances"][0][i] if results["distances"] else 0.0
                    document = results["documents"][0][i] if results["documents"] else ""

                    relevance = _cosine_from(distance, _space_of(collection))

                    if score_threshold is not None and relevance < score_threshold:
                        continue

                    row = _result_row(doc_id, metadata, document)
                    row["semantic_relevance"] = round(relevance, 4)
                    papers.append(row)

            return papers

        except Exception as e:
            logger.error(f"ChromaDB query failed: {e}")
            return []

    # ── reading the collection (the PaperListingPort capability) ────────────

    #: ChromaDB caps a `get`, so the listing walks it in pages.
    listing_page = 500

    def all_papers(self, collection_name: str = "papers") -> List[Dict[str, Any]]:
        """Every indexed paper, in no particular order, with no similarity.

        The corpus analyses used `query("research topic analysis", top_k=1000)`.
        ChromaDB clamps that to the collection size — but only while the limit
        *reaches* the collection. Past that, the answer is the thousand papers
        nearest that phrase, so clustering, trends and duplicates described a
        semantic neighbourhood of "research topic analysis", not the corpus.
        """
        try:
            collection = self.client.get_collection(collection_name)
        except Exception:
            logger.warning(f"Collection '{collection_name}' does not exist yet.")
            return []

        papers: List[Dict[str, Any]] = []
        offset = 0
        while True:
            try:
                page = collection.get(
                    limit=self.listing_page, offset=offset,
                    include=["documents", "metadatas"],
                )
            except Exception as e:
                logger.error(f"Could not read collection '{collection_name}': {e}")
                return papers

            ids = page.get("ids") or []
            if not ids:
                return papers

            metadatas = page.get("metadatas") or []
            documents = page.get("documents") or []
            for i, doc_id in enumerate(ids):
                papers.append(_result_row(
                    doc_id,
                    metadatas[i] if i < len(metadatas) else {},
                    documents[i] if i < len(documents) else "",
                ))

            offset += len(ids)
            if len(ids) < self.listing_page:
                return papers

    # ── chunk retrieval (the ChunkStorePort capability) ─────────────────────
    #
    # A separate collection rather than a `doc_type` field on `papers`: ChromaDB
    # has no `$exists` operator, and every document indexed by earlier runs
    # lacks that key, so filtering on it would empty `semantic_search` for the
    # whole back catalogue until a full reindex.

    def index_chunks(
        self, chunks: List[Dict[str, Any]], collection_name: str = "paper_chunks"
    ) -> bool:
        """Embed and store document fragments. Returns True on success."""
        if not chunks:
            return True

        try:
            collection = self._get_or_create_collection(collection_name)
            documents, metadatas, ids = [], [], []

            for chunk in chunks:
                text = str(chunk.get("text") or "").strip()
                chunk_id = str(chunk.get("chunk_id") or "")
                if not text or not chunk_id:
                    continue
                documents.append(text)
                # The paper's identity travels with the chunk so `chunk_search`
                # can name it: the parent_id is a derived id, not a readable one.
                metadatas.append({
                    "parent_id": _as_str(chunk.get("parent_id")),
                    "section": _as_str(chunk.get("section")),
                    "index": _as_int(chunk.get("index")),
                    "start": _as_int(chunk.get("start")),
                    "end": _as_int(chunk.get("end")),
                    "title": _as_str(chunk.get("title"))[:500],
                    "doi": _as_str(chunk.get("doi")),
                    "year": _as_str(chunk.get("year")),
                    "source": _as_str(chunk.get("source")),
                })
                ids.append(chunk_id)

            if not documents:
                logger.warning("No indexable chunks after filtering.")
                return True

            collection.upsert(documents=documents, metadatas=metadatas, ids=ids)
            logger.info(
                "Indexed %d chunks into '%s'.", len(documents), collection_name
            )
            return True

        except Exception as e:
            logger.error(f"Chunk indexing failed: {e}")
            return False

    def query_chunks(
        self, prompt: str, top_k: int = 10, collection_name: str = "paper_chunks"
    ) -> List[Dict[str, Any]]:
        """Return the chunks most similar to ``prompt``, with their metadata."""
        try:
            collection = self.client.get_collection(collection_name)
            count = collection.count()
            if count == 0:
                return []

            results = collection.query(
                query_texts=[prompt],
                n_results=min(top_k, count),
                include=["documents", "metadatas", "distances"],
            )

            out = []
            for i, chunk_id in enumerate(results["ids"][0] if results["ids"] else []):
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else 0.0
                out.append({
                    "chunk_id": chunk_id,
                    "parent_id": metadata.get("parent_id", ""),
                    "section": metadata.get("section", ""),
                    "index": metadata.get("index", 0),
                    "start": metadata.get("start", 0),
                    "end": metadata.get("end", 0),
                    "title": metadata.get("title", ""),
                    "doi": metadata.get("doi", ""),
                    "year": metadata.get("year", ""),
                    "source": metadata.get("source", ""),
                    "text": results["documents"][0][i] if results["documents"] else "",
                    "relevance": round(
                        _cosine_from(distance, _space_of(collection)), 4
                    ),
                })
            return out

        except Exception as e:
            logger.error(f"Chunk query failed: {e}")
            return []

    def has_chunks(self, parent_id: str, collection_name: str = "paper_chunks") -> bool:
        """Whether any chunk of ``parent_id`` is already indexed."""
        try:
            collection = self.client.get_collection(collection_name)
            found = collection.get(where={"parent_id": parent_id}, limit=1)
            return bool(found.get("ids"))
        except Exception:
            # A missing collection simply has no chunks.
            return False

    def delete_chunks(
        self,
        parent_id: str,
        collection_name: str = "paper_chunks",
        *,
        keep_ids: Sequence[str] = (),
    ) -> int:
        """Remove the chunks of ``parent_id`` that are not in ``keep_ids``."""
        try:
            collection = self.client.get_collection(collection_name)
            found = collection.get(where={"parent_id": parent_id})
            kept = set(keep_ids)
            ids = [i for i in (found.get("ids") or []) if i not in kept]
            if ids:
                collection.delete(ids=ids)
            return len(ids)
        except Exception as e:
            logger.error(f"Chunk deletion failed: {e}")
            return 0

    def list_collections(self) -> List[str]:
        """List all available collections."""
        try:
            return [c.name for c in self.client.list_collections()]
        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            return []

    def delete_collection(self, name: str) -> bool:
        """Delete a collection by name."""
        try:
            self.client.delete_collection(name)
            logger.info(f"Deleted ChromaDB collection '{name}'.")
            return True
        except Exception as e:
            logger.error(f"Failed to delete collection '{name}': {e}")
            return False

    def collection_stats(self, name: str = "papers") -> Dict[str, Any]:
        """Get statistics about a collection."""
        try:
            try:
                collection = self.client.get_collection(name)
            except Exception:
                return {"name": name, "count": 0, "status": "empty"}
            return {
                "name": name,
                "count": collection.count(),
                "metadata": collection.metadata or {},
            }
        except Exception as e:
            return {"name": name, "count": 0, "error": str(e)}

