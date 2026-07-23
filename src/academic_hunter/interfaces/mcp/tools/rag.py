"""MCP tools for RAG (Retrieval-Augmented Generation) over indexed papers."""

import logging
from typing import Optional

from academic_hunter import AcademicHunter
from academic_hunter.plugins.vector_stores import ChromaVectorStore

logger = logging.getLogger("academic_hunter.mcp.rag")


def _get_vector_store() -> Optional[ChromaVectorStore]:
    """Initialize the vector store using the hunter's output dir."""
    try:
        hunter = AcademicHunter()
        db_dir = str(hunter.output_dir.parent / ".academic_hunter" / "chroma_db")
        return ChromaVectorStore(db_dir=db_dir)
    except Exception as e:
        logger.warning(f"Could not initialize vector store: {e}")
        return None


def semantic_search(query: str, top_k: int = 10, score_threshold: float = 0.0) -> str:
    """
    Performs a semantic (embedding-based) search across all previously indexed papers.

    Use this tool when you want to find papers conceptually related to a topic,
    even if the exact keywords don't match. The search uses natural language understanding
    to find semantically similar content.

    Args:
        query: Natural language query describing what you're looking for.
        top_k: Maximum number of results to return (default 10, max 50).
        score_threshold: Minimum semantic relevance threshold 0.0-1.0 (default 0.0).

    Returns:
        A formatted string with semantically relevant papers and their relevance scores.
    """
    store = _get_vector_store()
    if store is None:
        return "Error: Vector store not available. Run a search first to index papers."

    top_k = min(top_k, 50)
    results = store.query(query, top_k=top_k, score_threshold=score_threshold)

    if not results:
        return (
            "No semantically relevant papers found. "
            "Try broadening your query, lowering the score_threshold, "
            "or run a new search first."
        )

    lines = [
        f"# Semantic Search Results\n",
        f"**Query:** {query}\n",
        f"**Results found:** {len(results)}\n",
        "---\n",
    ]

    for i, paper in enumerate(results, 1):
        lines.append(f"## {i}. {paper['title']}\n")
        lines.append(f"- **Semantic Relevance:** {paper['semantic_relevance']:.2%}")
        if paper.get("score"):
            lines.append(f" | **Keyword Score:** {paper['score']}")
        if paper.get("year"):
            lines.append(f" | **Year:** {paper['year']}")
        lines.append("\n")
        if paper.get("source"):
            lines.append(f"- **Source:** {paper['source']}\n")
        if paper.get("venue"):
            lines.append(f"- **Venue:** {paper['venue']}\n")
        if paper.get("doi"):
            lines.append(f"- **DOI:** `{paper['doi']}`\n")
        if paper.get("url"):
            lines.append(f"- **URL:** {paper['url']}\n")
        if paper.get("abstract_preview"):
            preview = paper["abstract_preview"][:300]
            lines.append(f"- **Preview:** {preview}...\n")
        lines.append("")

    return "\n".join(lines)


def index_papers() -> str:
    """
    Indexes the latest search results into the vector store for semantic queries.

    Run this after executing a search to enable semantic search capabilities.
    This is also called automatically at the end of each search pipeline run.
    """
    try:
        hunter = AcademicHunter()
        papers = list(hunter.consolidated_results.values())

        if not papers:
            return (
                "No papers found to index. Run a search first using `run_search`."
            )

        store = _get_vector_store()
        if store is None:
            return "Error: Could not initialize vector store."

        success = store.index_papers(papers)
        if success:
            return f"✅ Successfully indexed {len(papers)} papers for semantic search."
        else:
            return "Error: Failed to index papers."

    except Exception as e:
        return f"Error indexing papers: {str(e)}"


def vector_store_stats() -> str:
    """
    Shows statistics about the vector store: collection name, paper count, and status.

    Use this to check if papers have been indexed and how many are available for
    semantic search.
    """
    store = _get_vector_store()
    if store is None:
        return "Vector store not available."

    stats = store.collection_stats("papers")
    collections = store.list_collections()

    lines = ["# Vector Store Statistics\n"]
    lines.append(f"**Collections:** {', '.join(collections) if collections else 'None'}\n")
    if stats.get("count", 0) > 0:
        lines.append(f"**Papers indexed:** {stats['count']}\n")
        lines.append("✅ Vector store is ready for semantic queries.\n")
    else:
        lines.append(
            "⚠️  No papers indexed yet. Run a search, then use `index_papers` "
            "or the pipeline auto-indexes.\n"
        )

    return "\n".join(lines)


def ask_papers(question: str, top_k: int = 5) -> str:
    """
    Answers a research question using semantically retrieved papers as context.

    Use this tool when you want an AI-powered answer grounded in the actual papers
    stored in the vector database.

    Args:
        question: Your research question (e.g., "What do papers say about CBDC latency?").
        top_k: Number of papers to retrieve for context (default 5, max 20).

    Returns:
        Context retrieved from relevant papers, ready for an LLM to answer from.
    """
    store = _get_vector_store()
    if store is None:
        return "Error: Vector store not available. Run a search first."

    top_k = min(top_k, 20)
    results = store.query(question, top_k=top_k)

    if not results:
        return (
            f"No relevant papers found for: '{question}'. "
            "Try a different question or run a new search."
        )

    lines = [
        f"# Research Context\n",
        f"**Question:** {question}\n",
        f"**Retrieved {len(results)} papers as context:**\n",
        "---\n",
    ]

    for i, paper in enumerate(results, 1):
        lines.append(f"## Paper {i}: {paper['title']}\n")
        lines.append(f"**Relevance:** {paper['semantic_relevance']:.2%}")
        if paper.get("score"):
            lines.append(f" | **Keyword Score:** {paper['score']}")
        if paper.get("year"):
            lines.append(f" | **Year:** {paper['year']}")
        lines.append("\n")

        if paper.get("abstract_preview"):
            lines.append(f"{paper['abstract_preview']}\n")
        lines.append("")

    return "\n".join(lines)
