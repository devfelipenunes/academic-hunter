# Vector Stores Plugins (Native RAG)

Vector Stores act as the long-term, queryable memory of the Academic Hunter engine.
Instead of just exporting raw `.csv` or `.md` files at the end of a pipeline, Vector Stores transform papers into high-dimensional embeddings.

This is the foundation for building **Native RAG (Retrieval-Augmented Generation)** capabilities directly into the engine or exposing them via the MCP server.

## Base Architecture
All Vector Stores must inherit from `BaseVectorStore` (`src/academic_hunter/plugins/vector_stores/base_store.py`).

They require two core methods:
1. `index_papers(papers)`: Converts a batch of papers into embeddings and saves them.
2. `query(prompt, top_k)`: Performs a semantic similarity search against the saved database.

## Available Stores

### 1. `ChromaVectorStore`
Integrates with `chromadb`. Data is saved locally inside the `.academic_hunter/chroma_db/` directory.
- **Use Case:** Best for small to medium systematic reviews (up to 100k papers) where simplicity and local persistence are key.

## Future Possibilities
Because of this plugin architecture, contributors can easily add `FaissVectorStore`, `PineconeVectorStore`, or `LanceDBVectorStore` without modifying a single line of the `manager.py` orchestration logic.
