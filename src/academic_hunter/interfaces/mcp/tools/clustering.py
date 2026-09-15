"""MCP tools for topic clustering of indexed papers using BERTopic.

BERTopic is an optional dependency — the module stays importable without it,
and the tool function returns a graceful message when it is missing.
"""

import logging

from academic_hunter.core.nlp.model_cache import get_sentence_transformer
from mcp.server.fastmcp import Context

from ._utils import _get_vector_store, corpus_of, run_blocking

logger = logging.getLogger("academic_hunter.mcp.clustering")


def _load_bertopic():
    """Imported on use: BERTopic pulls in umap, hdbscan and scikit-learn.

    At module scope it cost 16 s of the MCP server's startup — measured, and
    the whole of it — for a tool most sessions never call.
    """
    from bertopic import BERTopic

    return BERTopic


async def cluster_papers(
    ctx: Context, top_k: int = 500, min_cluster_size: int = 3
) -> str:
    """Clusters indexed papers by topic using BERTopic with MiniLM embeddings.

    Returns a formatted Markdown report of topic clusters with representative
    paper titles for each cluster.  Outliers (noise points) are counted but
    excluded from the per-cluster listings.

    Parameters
    ----------
    ctx : Context
        FastMCP Context (auto-injected by the MCP runtime).
    top_k : int
        Number of papers to retrieve from the vector store (default 500).
    min_cluster_size : int
        Minimum papers required to form a topic cluster (default 3).

    Returns
    -------
    str
        Markdown report or a user-facing message when clustering is not
        possible (no papers, no vector store, BERTopic not installed, etc.).
    """
    await ctx.info(f"Clustering up to {top_k} papers (min cluster size: {min_cluster_size})...")

    # ── Retrieve papers from the vector store ───────────────────────────────
    store = _get_vector_store()
    if store is None:
        await ctx.error("Vector store not available")
        return "Vector store not available. Index papers first."

    results = corpus_of(store, top_k)
    if not results:
        await ctx.info("No papers found in vector store")
        return "No papers found to cluster. Index papers first."

    # ── Guard: BERTopic available? ──────────────────────────────────────────
    try:
        BERTopic = await run_blocking(_load_bertopic)
    except ImportError:
        await ctx.error("BERTopic is not installed")
        return (
            "BERTopic is not installed. "
            "Install it with: pip install bertopic umap-learn hdbscan"
        )

    await ctx.info(f"Retrieved {len(results)} papers, running BERTopic...")

    # ── Prepare documents ───────────────────────────────────────────────────
    documents = []
    for paper in results:
        title = paper.get("title", "")
        abstract = paper.get("abstract_preview", "")
        text = f"{title}. {abstract}" if abstract else title
        documents.append(text)

    if len(documents) < min_cluster_size:
        await ctx.info("Too few papers to cluster")
        return (
            f"Too few papers ({len(documents)}) to cluster. "
            f"Need at least {min_cluster_size}."
        )

    # ── Run BERTopic ────────────────────────────────────────────────────────
    try:
        embedding_model = await run_blocking(get_sentence_transformer)
        if embedding_model is None:
            raise ImportError("sentence-transformers")
        topic_model = BERTopic(
            embedding_model=embedding_model,
            min_topic_size=min_cluster_size,
            verbose=False,
        )
        topics, _ = await run_blocking(topic_model.fit_transform, documents)

        # ── Build report ────────────────────────────────────────────────────
        n_topics = len({t for t in topics if t != -1})
        n_outliers = sum(1 for t in topics if t == -1)

        lines = [
            "# Topic Clusters\n",
            f"**Papers analyzed:** {len(documents)}\n",
            f"**Topics found:** {n_topics}\n",
            f"**Outliers (unassigned):** {n_outliers}\n",
            "---\n",
        ]

        for topic_id in sorted(set(topics)):
            if topic_id == -1:
                continue  # Outlier / noise cluster

            words = topic_model.get_topic(topic_id)
            if not words:
                continue

            top_words = ", ".join(w for w, _ in words[:8])
            paper_indices = [i for i, t in enumerate(topics) if t == topic_id]
            sample_titles = [
                f"- {results[idx].get('title', 'Untitled')}"
                for idx in paper_indices[:5]
            ]

            lines.append(f"## Topic {topic_id}: {top_words}\n")
            lines.append(f"**Papers:** {len(paper_indices)}\n")
            lines.extend(sample_titles)
            if len(paper_indices) > 5:
                lines.append(f"  *... and {len(paper_indices) - 5} more*")
            lines.append("")

        await ctx.info(
            f"Found {n_topics} topics across {len(documents)} papers"
        )
        return "\n".join(lines)

    except Exception as e:
        await ctx.error(f"Clustering failed: {e}")
        return f"Clustering failed: {e}"
