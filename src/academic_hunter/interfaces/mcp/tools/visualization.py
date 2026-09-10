"""MCP tools for research landscape visualization using UMAP and BERTopic.

Provides visualize_landscape and topic_evolution tools.
"""

import json
import logging

from mcp.server.fastmcp import Context

from ._utils import _get_vector_store

logger = logging.getLogger("academic_hunter.mcp.visualization")

# Module-level BERTopic reference so that unittest.mock.patch can target it.
# BERTopic is never used outside the tool function, but a module-level name
# allows clean patching in tests without interfering with sys.modules.
try:
    from bertopic import BERTopic
except ImportError:
    BERTopic = None

# Module-level reference for UMAP so that unittest.mock.patch can target it
# from the test suite. SentenceTransformer is reached through the shared cache
# instead; tests patch `visualization.get_sentence_transformer`.
try:
    import umap
except ImportError:
    umap = None

from academic_hunter.core.nlp.model_cache import get_sentence_transformer


async def visualize_landscape(ctx: Context, top_k: int = 500, n_neighbors: int = 15) -> str:
    """Generates a 2D UMAP projection of the paper embedding space.

    Returns a JSON array of 2D coordinates with paper metadata for
    interactive visualization by the client.

    Args:
        ctx: FastMCP Context (auto-injected).
        top_k: Max papers to include (default 500).
        n_neighbors: UMAP neighborhood size (default 15).
    """
    await ctx.info(f"Generating landscape visualization for {top_k} papers...")

    store = _get_vector_store()
    if store is None:
        await ctx.error("Vector store not available")
        return "Vector store not available."

    results = store.query("research paper topic analysis", top_k=top_k)
    if not results or len(results) < 5:
        await ctx.info("Too few papers for visualization")
        return "Not enough papers for a meaningful visualization."

    if umap is None:
        await ctx.error("UMAP is not installed")
        return "Required library not installed: umap-learn. Install with: pip install umap-learn"

    model = get_sentence_transformer()
    if model is None:
        await ctx.error("SentenceTransformer is not installed")
        return "Required library not installed: sentence-transformers"

    try:
        import numpy as np

        texts = [f"{p.get('title','')} {p.get('abstract_preview','')}" for p in results]
        embeddings = model.encode(texts)

        reducer = umap.UMAP(n_neighbors=min(n_neighbors, len(results) - 1), min_dist=0.1, random_state=42)
        coords_2d = reducer.fit_transform(embeddings)

        # Build JSON output with coordinates + metadata
        points = []
        for i, paper in enumerate(results):
            points.append({
                "x": float(coords_2d[i, 0]),
                "y": float(coords_2d[i, 1]),
                "title": paper.get("title", "Untitled"),
                "year": paper.get("year"),
                "doi": paper.get("doi", ""),
                "relevance": paper.get("semantic_relevance", 0),
            })

        output = {"papers": points, "shape": list(embeddings.shape)}
        await ctx.info(f"Visualization generated: {len(points)} points in 2D")
        return json.dumps(output, ensure_ascii=False)

    except ImportError as e:
        await ctx.error(f"Missing dependency: {e}")
        return f"Required library not installed: {e}"
    except Exception as e:
        await ctx.error(f"Visualization failed: {e}")
        return f"Visualization failed: {e}"


async def topic_evolution(ctx: Context, top_k: int = 500) -> str:
    """Shows how research topics have evolved over time using BERTopic.

    Groups papers by year and tracks topic composition changes.

    Args:
        ctx: FastMCP Context (auto-injected).
        top_k: Number of papers to analyze (default 500).
    """
    await ctx.info("Analyzing topic evolution over time...")

    store = _get_vector_store()
    if store is None:
        await ctx.error("Vector store not available")
        return "Vector store not available."

    results = store.query("research topic analysis", top_k=top_k)
    if not results or len(results) < 5:
        await ctx.info("Too few papers for evolution analysis")
        return "Not enough papers for evolution analysis."

    if BERTopic is None:
        await ctx.error("BERTopic is not installed")
        return (
            "BERTopic not installed. "
            "Install it with: pip install bertopic umap-learn hdbscan"
        )

    model = get_sentence_transformer()
    if model is None:
        await ctx.error("SentenceTransformer is not installed")
        return "Required library not installed: sentence-transformers"

    try:
        from collections import defaultdict

        documents = []
        years = []
        for p in results:
            title = p.get("title", "")
            abstract = p.get("abstract_preview", "")
            text = f"{title}. {abstract}" if abstract else title
            documents.append(text)
            year = p.get("year", 0)
            years.append(int(year) if year else 0)

        topic_model = BERTopic(embedding_model=model, min_topic_size=3, verbose=False)
        topics, _ = topic_model.fit_transform(documents)

        # Group by year and topic
        year_topic = defaultdict(lambda: defaultdict(int))
        for i, (topic, year) in enumerate(zip(topics, years)):
            if topic != -1 and year > 0:
                year_topic[year][topic] += 1

        lines = ["# Topic Evolution Over Time\n", f"**Papers analyzed:** {len(documents)}\n", "---\n"]

        for year in sorted(year_topic.keys()):
            topics_in_year = year_topic[year]
            total = sum(topics_in_year.values())
            top_topics = sorted(topics_in_year.items(), key=lambda x: -x[1])[:3]
            topic_labels = []
            for tid, count in top_topics:
                words = topic_model.get_topic(tid)
                label = ", ".join(w for w, _ in words[:3]) if words else f"Topic {tid}"
                topic_labels.append(f"{label} ({count})")
            lines.append(f"### {year} — {total} papers\n")
            lines.append("- " + "\n- ".join(topic_labels) + "\n\n")

        await ctx.info(f"Evolution analysis complete ({len(year_topic)} years)")
        return "\n".join(lines)

    except ImportError as e:
        await ctx.error(f"Missing dependency: {e}")
        return f"Required library: {e}"
    except Exception as e:
        await ctx.error(f"Evolution analysis failed: {e}")
        return f"Evolution analysis failed: {e}"
