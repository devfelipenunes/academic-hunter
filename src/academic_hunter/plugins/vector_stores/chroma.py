"""ChromaDB vector store for RAG on academic papers.

Uses ONNX-based all-MiniLM-L6-v2 embeddings via ChromaDB's DefaultEmbeddingFunction.
"""

import hashlib
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseVectorStore

logger = logging.getLogger("academic_hunter.vector_store")


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
                metadata={"created": datetime.now().isoformat(), "type": "academic_papers"},
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
                    "doi": doi,
                    "year": str(paper.get("Year", "")),
                    "source": str(paper.get("Source", "")),
                    "score": float(paper.get("Relevance_Score", 0.0)),
                    "citations": int(paper.get("Citations", 0)),
                    "venue": str(paper.get("Venue", "")),
                    "anchor_category": str(paper.get("Anchor_Category", "")),
                    "tech_category": str(paper.get("Tech_Category", "")),
                    "url": str(paper.get("URL", "")),
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

                    relevance = max(0.0, min(1.0, (1.414 - distance) / 1.414))

                    if score_threshold is not None and relevance < score_threshold:
                        continue

                    title = metadata.get("title", document.split("\n")[0] if document else doc_id)

                    papers.append({
                        "id": doc_id,
                        "title": title,
                        "doi": metadata.get("doi", ""),
                        "year": metadata.get("year", ""),
                        "source": metadata.get("source", ""),
                        "score": metadata.get("score", 0.0),
                        "citations": metadata.get("citations", 0),
                        "venue": metadata.get("venue", ""),
                        "url": metadata.get("url", ""),
                        "semantic_relevance": round(relevance, 4),
                        "abstract_preview": document[:500] if document else "",
                    })

            return papers

        except Exception as e:
            logger.error(f"ChromaDB query failed: {e}")
            return []

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
