"""MCP tools for topic clustering of indexed papers using BERTopic.

BERTopic is an optional dependency — the module stays importable without it,
and the tool function returns a graceful message when it is missing.
"""

import logging
from mcp.server.fastmcp import Context

logger = logging.getLogger("academic_hunter.mcp.clustering")

# Module-level BERTopic reference so that unittest.mock.patch can target it.
# BERTopic is never used outside the tool function, but a module-level name
# allows clean patching in tests without interfering with sys.modules.
try:
    from bertopic import BERTopic
except ImportError:
    BERTopic = None


def _get_vector_store():
    """Initialize the ChromaDB vector store (same lazy pattern as rag.py).

    Returns None when ChromaDB is unavailable so the caller can degrade
    gracefully.
    """
    try:
        from academic_hunter import AcademicHunter
        from academic_hunter.plugins.vector_stores import ChromaVectorStore
        from ._utils import get_project_root

        hunter = AcademicHunter(output_dir=str(get_project_root() / "results"))
        db_dir = str(hunter.output_dir.parent / ".academic_hunter" / "chroma_db")
        return ChromaVectorStore(db_dir=db_dir)
    except Exception:
        return None


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

    results = store.query("research topic analysis", top_k=top_k)
    if not results:
        await ctx.info("No papers found in vector store")
        return "No papers found to cluster. Index papers first."

    # ── Guard: BERTopic available? ──────────────────────────────────────────
    if BERTopic is None:
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
        from sentence_transformers import SentenceTransformer

        embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        topic_model = BERTopic(
            embedding_model=embedding_model,
            min_topic_size=min_cluster_size,
            verbose=False,
        )
        topics, _ = topic_model.fit_transform(documents)

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
