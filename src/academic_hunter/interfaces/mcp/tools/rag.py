"""MCP tools for RAG (Retrieval-Augmented Generation) over indexed papers.

All tools accept a ``ctx: Context`` parameter (auto-injected by FastMCP)
for logging and progress reporting.
"""

import logging

from academic_hunter.core.nlp.reranker import rerank_texts
from mcp.server.fastmcp import Context

from ..exceptions import VectorStoreError
from ._utils import (
    _get_vector_store,
    _load_latest_papers,
    _make_hunter,
    read_store_stats,
    run_blocking,
)

logger = logging.getLogger("academic_hunter.mcp.rag")


def _opening(text: str, limit: int = 250) -> str:
    """The opening of ``text``, ending on a sentence rather than mid-word.

    The preview was already truncated to 500 characters when the paper was
    indexed (``plugins/vector_stores/chroma.py``), so slicing at 250 lands inside
    a sentence -- and read under a heading, that half-sentence is taken for a
    finding the retrieval never made. Cutting at the last sentence end that fits
    keeps the excerpt a whole statement.

    When even the first sentence overruns the limit the excerpt is returned as
    indexed instead of clipped: this is a retrieved abstract, not a generated
    claim, and half a sentence is worse than a long one.
    """
    text = text.strip()
    if len(text) <= limit:
        return text
    window = text[:limit]
    cut = max(window.rfind(". "), window.rfind("? "), window.rfind("! "))
    if cut < 0:
        return text
    return window[: cut + 1]


async def semantic_search(
    query: str, top_k: int = 20, score_threshold: float = 0.0, ctx: Context = None
) -> str:
    """Performs a semantic (embedding-based) search across all previously indexed papers.

    Use this tool when you want to find papers conceptually related to a topic,
    even if the exact keywords don't match.

    Args:
        ctx: FastMCP Context (auto-injected).
        query: Natural language query describing what you're looking for.
        top_k: Maximum number of results to return (default 20, max 50).
        score_threshold: Minimum semantic relevance threshold 0.0-1.0 (default 0.0).
    """
    await ctx.info(f"Semantic search for: '{query}'...")
    store = await run_blocking(_get_vector_store)
    if store is None:
        await ctx.error("Vector store not available")
        raise VectorStoreError(
            "Vector store not available. Run a search first to index papers."
        )

    top_k = min(top_k, 50)
    results = await run_blocking(
        store.query, query, top_k=top_k, score_threshold=score_threshold
    )

    if not results:
        await ctx.info("No semantically relevant papers found")
        return (
            "No semantically relevant papers found. "
            "Try broadening your query, lowering the score_threshold, "
            "or run a new search first."
        )

    lines = [
        "# Semantic Search Results\n",
        f"**Query:** {query}\n",
        f"**Results found:** {len(results)}\n",
        "---\n",
    ]

    for i, paper in enumerate(results, 1):
        lines.append(f"## {i}. {paper['title']}\n")
        lines.append(f"- **Semantic Relevance:** {paper['semantic_relevance']:.2%}")
        if paper.get("score"):
            lines.append(f" | **Relevance Score:** {paper['score']}")
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
        hunter = await run_blocking(_make_hunter)
        papers = list(hunter.consolidated_results.values())

        if not papers:
            await ctx.info("No in-memory results, reading the latest run...")
            papers = await run_blocking(_load_latest_papers)

        if not papers:
            await ctx.info("No papers found to index")
            return (
                "No papers found to index. Run a search first using `run_search`."
            )

        store = await run_blocking(_get_vector_store)
        if store is None:
            await ctx.error("Could not initialize vector store")
            raise VectorStoreError("Could not initialize vector store.")

        await ctx.report_progress(0, 1, f"Indexing {len(papers)} papers...")
        success = await run_blocking(store.index_papers, papers)
        await ctx.report_progress(1, 1, "Indexing complete")

        if success:
            await ctx.info(f"Successfully indexed {len(papers)} papers")
            return f"✅ Successfully indexed {len(papers)} papers for semantic search."
        else:
            await ctx.error("Failed to index papers")
            raise VectorStoreError("Failed to index papers.")

    except VectorStoreError:
        raise
    except Exception as e:
        await ctx.error(f"Failed to index papers: {e}")
        raise VectorStoreError(str(e))


async def vector_store_stats(ctx: Context = None) -> str:
    """Shows every collection in the vector store, with its paper count.

    One collection per review, so this is the list of reviews this installation
    has searched and how big each corpus is. The **active** one — marked below —
    is the collection ``settings.collection_name`` points at, and it is the one
    `semantic_search`, `answer_question` and every corpus analysis read. The others are
    older reviews, or the shared ``papers`` collection that predates one
    collection per review; remove one with `delete_collection`.

    A count of zero on the active collection means nothing is indexed for this
    review yet: run a search, then use `index_papers`, or let the pipeline
    auto-index.

    Args:
        ctx: FastMCP Context (auto-injected).
    """
    await ctx.info("Checking vector store statistics...")
    store = await run_blocking(_get_vector_store)
    if store is None:
        await ctx.info("Vector store not available")
        return "Vector store not available."

    collections, data, total = await run_blocking(read_store_stats, store)
    active = getattr(store, "default_collection", "")
    counts = dict(zip(collections, data))

    lines = ["# Vector Store Statistics\n"]
    if not collections:
        lines.append(
            "No collections yet. Run a search, then use `index_papers`, or let "
            "the pipeline auto-index.\n"
        )
        return "\n".join(lines)

    lines.append(f"**Collection in use:** `{active}`\n")
    lines.append(f"**Papers in it:** {counts.get(active, {}).get('count', 0)}\n")
    lines.append(f"**Papers across all collections:** {total}\n")
    lines.append("\n## Collections\n")
    for name in collections:
        count = counts.get(name, {}).get("count", 0)
        marker = "  ← this review" if name == active else ""
        lines.append(f"- `{name}`: {count} papers{marker}")

    if active not in counts:
        lines.append(
            f"\nThe active collection `{active}` does not exist yet, so a search "
            "here would find nothing. Index with `index_papers`, or run a search "
            "and let the pipeline do it."
        )
    elif not counts[active].get("count", 0):
        lines.append(
            f"\n`{active}` is empty: nothing is indexed for this review yet. "
            "Index with `index_papers`, or run a search and let the pipeline "
            "index the results."
        )
    lines.append("")
    lines.append("Remove one with `delete_collection`; that cannot be undone.")

    await ctx.info(f"{len(collections)} collection(s), {total} papers in total")
    return "\n".join(lines)


async def delete_collection(collection: str, confirm: bool = False,
                            ctx: Context = None) -> str:
    """Deletes a vector-store collection and every paper in it. Irreversible.

    One collection per review, so over time an installation accumulates one per
    search that was ever run. This removes one. List them with
    `vector_store_stats` first -- the count is shown there, and this tool will not
    tell you what you lost after the fact.

    Deleting the collection the current configuration points at is allowed: the
    next run re-indexes into it, so it is how a review's corpus is cleared before
    a re-run. Nothing else points back at it, and the papers themselves are not
    lost from disk -- the run's CSV in ``results/`` still holds them.

    Args:
        collection: Exact collection name, as `vector_store_stats` spells it.
        confirm: Must be True. Without it nothing is deleted and the tool says
            what it would have removed.
        ctx: FastMCP Context (auto-injected).
    """
    store = await run_blocking(_get_vector_store)
    if store is None:
        await ctx.info("Vector store not available")
        return "Vector store not available."

    collections = await run_blocking(store.list_collections)
    if collection not in collections:
        known = ", ".join(f"`{name}`" for name in collections) or "none"
        return (
            f"No collection named `{collection}`. Nothing was deleted. In this "
            f"store: {known}."
        )

    stats = await run_blocking(store.collection_stats, collection)
    count = stats.get("count", 0)
    active = getattr(store, "default_collection", "")

    if not confirm:
        note = (
            f" `{collection}` is the collection this review reads, so the next "
            "run will re-index into it from scratch." if collection == active else ""
        )
        return (
            f"`{collection}` holds {count} papers and nothing was deleted.{note} "
            f"Call again with confirm=true to remove it."
        )

    await ctx.report_progress(0, 1, f"Deleting {collection}...")
    deleted = await run_blocking(store.delete_collection, collection)
    await ctx.report_progress(1, 1, "Deletion complete")

    if not deleted:
        await ctx.error(f"Could not delete collection {collection}")
        raise VectorStoreError(
            f"ChromaDB refused to delete `{collection}`. Nothing was removed."
        )

    await ctx.info(f"Deleted {collection}")
    return f"✅ Deleted `{collection}` and its {count} papers."


async def answer_question(question: str, top_k: int = 15, ctx: Context = None) -> str:
    """Retrieves the papers that best match a question and quotes their abstracts.

    Nothing here reads the abstracts and answers the question: what comes back is
    the most relevant indexed papers, their abstracts as indexed, and their titles
    and DOIs to cite. The reading is the caller's. The description this tool used
    to publish promised a composed answer, which described a tool that does not
    exist — and the headings said the same thing.

    Use it to gather citable sources on a question. Works best after papers have
    been indexed via ``index_papers`` or after running the automatic pipeline.

    Args:
        question: The research question to retrieve papers for.
        top_k: Number of papers to retrieve for context (default 15, max 20).
        ctx: FastMCP Context (auto-injected).
    """
    await ctx.info(f"Answering question: '{question}'")
    store = await run_blocking(_get_vector_store)
    if store is None:
        await ctx.error("Vector store not available")
        raise VectorStoreError("Vector store not available. Run a search first.")

    top_k = min(top_k, 20)
    results = await run_blocking(store.query, question, top_k=top_k)

    if not results:
        await ctx.info(f"No relevant papers found for: '{question}'")
        return (
            f"No relevant papers found for: '{question}'. "
            "Try a different question or run a new search."
        )

    findings: list[str] = []
    citations: list[str] = []

    for paper in results:
        title = paper.get("title", "Unknown")
        doi = paper.get("doi", "")
        preview = paper.get("abstract_preview", "")

        finding = _opening(preview) if preview else "No abstract available."
        findings.append(f"- {finding}")

        if doi:
            citations.append(f"- **{title}** — DOI: `{doi}`")
        else:
            citations.append(f"- **{title}**")

    lines = [
        "# Retrieved Context\n",
        f"**Question:** {question}\n",
        f"**Papers consulted:** {len(results)}\n",
        "---\n",
        "## Retrieved Abstracts\n",
        *findings,
        "",
        "## Sources\n",
        *citations,
        "",
        "---",
        "*These abstracts were retrieved from the indexed paper database; no answer was generated.*",
    ]

    await ctx.info(f"Answered question using {len(results)} papers")
    return "\n".join(lines)


async def rerank_search(ctx: Context, query: str, top_k: int = 20, rerank_k: int = 5) -> str:
    """Semantic search with optional cross-encoder re-ranking for higher precision.

    Uses bi-encoder (MiniLM) for initial retrieval, then optionally re-ranks
    top results with cross-encoder if ``sentence-transformers`` is installed.

    Args:
        ctx: FastMCP Context (auto-injected).
        query: Search query.
        top_k: Initial results from bi-encoder (default 20).
        rerank_k: Final results after re-ranking (default 5).
    """
    await ctx.info(f"Running re-ranked search for: '{query[:60]}'...")
    store = await run_blocking(_get_vector_store)
    if store is None:
        await ctx.error("Vector store not available")
        raise VectorStoreError("Vector store not available.")

    results = await run_blocking(store.query, query, top_k=top_k)
    if not results:
        await ctx.info("No results found")
        return "No semantically relevant papers found."

    texts = [f"{p.get('title','')} {p.get('abstract_preview','')}" for p in results]
    try:
        scores = await run_blocking(rerank_texts, query, texts)
    except Exception as e:
        await ctx.warning(f"Cross-encoder failed ({e}), using bi-encoder results")
    else:
        if scores is None:
            await ctx.info("Cross-encoder not installed, using bi-encoder results")
        else:
            order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
            results = [results[i] for i in order[:rerank_k]]
            await ctx.info(f"Cross-encoder re-ranked {len(scores)} candidates")

    lines = ["# Re-Ranked Search Results\n", f"**Query:** {query}\n",
             f"**Results:** {len(results)}\n", "---\n"]
    for i, paper in enumerate(results, 1):
        title = paper.get("title", "Untitled")
        score = paper.get("semantic_relevance", 0)
        year = paper.get("year", "?")
        doi = paper.get("doi", "")
        lines.append(f"## {i}. {title}\n")
        lines.append(f"- **Relevance:** {score:.1%} | **Year:** {year}\n")
        if doi: lines.append(f"- **DOI:** `{doi}`\n")
        if paper.get("abstract_preview"):
            lines.append(f"- {paper['abstract_preview'][:200]}...\n")
        lines.append("")
    await ctx.info(f"Returning {len(results)} re-ranked papers")
    return "\n".join(lines)
