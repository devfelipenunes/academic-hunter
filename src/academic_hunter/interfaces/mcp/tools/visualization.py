"""MCP tools for research landscape visualization using BERTopic.

Provides the topic_evolution tool.
"""

import logging

from academic_hunter.core.nlp.model_cache import get_sentence_transformer
from mcp.server.fastmcp import Context

from ._utils import _get_vector_store, corpus_of, run_blocking

logger = logging.getLogger("academic_hunter.mcp.visualization")


def _load_bertopic():
    """Imported on use: BERTopic pulls in numba and scikit-learn.

    At module scope these cost seconds of the MCP server's startup — measured —
    for a tool most sessions never call.
    """
    from bertopic import BERTopic

    return BERTopic


async def topic_evolution(ctx: Context, top_k: int = 500) -> str:
    """Shows how research topics have evolved over time using BERTopic.

    Groups papers by year and tracks topic composition changes.

    Args:
        ctx: FastMCP Context (auto-injected).
        top_k: Number of papers to analyze (default 500).
    """
    await ctx.info("Analyzing topic evolution over time...")

    store = await run_blocking(_get_vector_store)
    if store is None:
        await ctx.error("Vector store not available")
        return "Vector store not available."

    results = (await run_blocking(corpus_of, store, top_k))[:top_k]
    if not results or len(results) < 5:
        await ctx.info("Too few papers for evolution analysis")
        return "Not enough papers for evolution analysis."

    try:
        bertopic_cls = await run_blocking(_load_bertopic)
    except ImportError:
        await ctx.error("BERTopic is not installed")
        return (
            "BERTopic not installed. Install the extra: "
            "pip install 'academic-hunter[ml]'"
        )

    model = await run_blocking(get_sentence_transformer)
    if model is None:
        await ctx.error("SentenceTransformer is not installed")
        return (
            "Required library not installed: sentence-transformers. "
            "Install the extra: pip install 'academic-hunter[ml]'"
        )

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

        topic_model = bertopic_cls(embedding_model=model, min_topic_size=3, verbose=False)
        topics, _ = await run_blocking(topic_model.fit_transform, documents)

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
