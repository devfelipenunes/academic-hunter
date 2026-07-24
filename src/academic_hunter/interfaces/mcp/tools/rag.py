"""MCP tools for RAG (Retrieval-Augmented Generation) over indexed papers.

All tools accept a ``ctx: Context`` parameter (auto-injected by FastMCP)
for logging and progress reporting.
"""

import logging
from typing import Optional
from mcp.server.fastmcp import Context

from academic_hunter import AcademicHunter
from academic_hunter.plugins.vector_stores import ChromaVectorStore
from ._utils import get_project_root
from ..exceptions import VectorStoreError

logger = logging.getLogger("academic_hunter.mcp.rag")


def _make_hunter() -> AcademicHunter:
    """Create an AcademicHunter rooted at the project directory."""
    return AcademicHunter(output_dir=str(get_project_root() / "results"))


def _get_vector_store() -> Optional[ChromaVectorStore]:
    """Initialize the vector store using the hunter's output dir."""
    try:
        hunter = _make_hunter()
        db_dir = str(hunter.output_dir.parent / ".academic_hunter" / "chroma_db")
        return ChromaVectorStore(db_dir=db_dir)
    except Exception as e:
        logger.warning(f"Could not initialize vector store: {e}")
        return None


async def semantic_search(
    query: str, top_k: int = 10, score_threshold: float = 0.0, ctx: Context = None
) -> str:
    """Performs a semantic (embedding-based) search across all previously indexed papers.

    Use this tool when you want to find papers conceptually related to a topic,
    even if the exact keywords don't match.

    Args:
        ctx: FastMCP Context (auto-injected).
        query: Natural language query describing what you're looking for.
        top_k: Maximum number of results to return (default 10, max 50).
        score_threshold: Minimum semantic relevance threshold 0.0-1.0 (default 0.0).
    """
    await ctx.info(f"Semantic search for: '{query}'...")
    store = _get_vector_store()
    if store is None:
        await ctx.error("Vector store not available")
        return "Error: Vector store not available. Run a search first to index papers."

    top_k = min(top_k, 50)
    results = store.query(query, top_k=top_k, score_threshold=score_threshold)

    if not results:
        await ctx.info("No semantically relevant papers found")
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

    await ctx.info(f"Found {len(results)} semantically relevant papers")
    return "\n".join(lines)


async def index_papers(ctx: Context = None) -> str:
    """Indexes the latest search results into the vector store for semantic queries.

    Run this after executing a search to enable semantic search capabilities.
    This is also called automatically at the end of each search pipeline run.
    """
    await ctx.info("Indexing papers into vector store...")
    try:
        hunter = _make_hunter()
        papers = list(hunter.consolidated_results.values())

        if not papers:
            await ctx.info("No papers found to index")
            return (
                "No papers found to index. Run a search first using `run_search`."
            )

        store = _get_vector_store()
        if store is None:
            await ctx.error("Could not initialize vector store")
            return "Error: Could not initialize vector store."

        await ctx.report_progress(0, 1, f"Indexing {len(papers)} papers...")
        success = store.index_papers(papers)
        await ctx.report_progress(1, 1, "Indexing complete")

        if success:
            await ctx.info(f"Successfully indexed {len(papers)} papers")
            return f"✅ Successfully indexed {len(papers)} papers for semantic search."
        else:
            await ctx.error("Failed to index papers")
            return "Error: Failed to index papers."

    except VectorStoreError:
        raise
    except Exception as e:
        await ctx.error(f"Failed to index papers: {e}")
        raise VectorStoreError(str(e))


async def vector_store_stats(ctx: Context = None) -> str:
    """Shows statistics about the vector store: collection name, paper count, and status.

    Use this to check if papers have been indexed and how many are available for
    semantic search.
    """
    await ctx.info("Checking vector store statistics...")
    store = _get_vector_store()
    if store is None:
        await ctx.info("Vector store not available")
        return "Vector store not available."

    stats = store.collection_stats("papers")
    collections = store.list_collections()

    lines = ["# Vector Store Statistics\n"]
    lines.append(
        f"**Collections:** {', '.join(collections) if collections else 'None'}\n"
    )
    if stats.get("count", 0) > 0:
        lines.append(f"**Papers indexed:** {stats['count']}\n")
        lines.append("✅ Vector store is ready for semantic queries.\n")
    else:
        lines.append(
            "⚠️  No papers indexed yet. Run a search, then use `index_papers` "
            "or the pipeline auto-indexes.\n"
        )

    await ctx.info(f"Vector store has {stats.get('count', 0)} papers")
    return "\n".join(lines)


async def ask_papers(question: str, top_k: int = 5, ctx: Context = None) -> str:
    """Answers a research question using semantically retrieved papers as context.

    Use this tool when you want an AI-powered answer grounded in the actual papers
    stored in the vector database.

    Args:
        ctx: FastMCP Context (auto-injected).
        question: Your research question (e.g., "What do papers say about CBDC latency?").
        top_k: Number of papers to retrieve for context (default 5, max 20).
    """
    await ctx.info(f"Retrieving context for: '{question}'...")
    store = _get_vector_store()
    if store is None:
        await ctx.error("Vector store not available")
        return "Error: Vector store not available. Run a search first."

    top_k = min(top_k, 20)
    results = store.query(question, top_k=top_k)

    if not results:
        await ctx.info(f"No relevant papers found for: '{question}'")
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

    await ctx.info(f"Retrieved {len(results)} papers as context")
    return "\n".join(lines)
