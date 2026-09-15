"""MCP tool for trending-topic analysis — extracts keyword bigrams from indexed papers.

Accepts a ``ctx: Context`` parameter (auto-injected by FastMCP)
for logging and progress reporting.
"""

import logging
import re
from collections import Counter

from mcp.server.fastmcp import Context

from ._utils import _STOPWORDS, _get_vector_store, corpus_of

logger = logging.getLogger("academic_hunter.mcp.trending")


def _extract_bigrams(title: str, stopwords: set) -> list[str]:
    """Extract meaningful bigrams from a title, excluding stopwords."""
    words = re.findall(r"[a-zA-Z][a-zA-Z\-]{1,}", title.lower())
    filtered = [w for w in words if w not in stopwords and len(w) > 2]
    bigrams = []
    for i in range(len(filtered) - 1):
        bigrams.append(f"{filtered[i]} {filtered[i+1]}")
    return bigrams


async def trending_topics(ctx: Context, days: int = 30, min_papers: int = 3) -> str:
    """Analyzes indexed papers to identify trending research topics.

    Extracts keyword bigrams from paper titles, groups related papers,
    and returns the top clusters by frequency.

    Args:
        ctx: FastMCP Context (auto-injected).
        days: Lookback window for papers to consider (default 30, currently unused
              since vector store does not filter by date).
        min_papers: Minimum papers sharing a bigram to be considered a trend
                    (default 3).
    """
    await ctx.info("Analyzing trending topics from indexed papers...")
    store = _get_vector_store()
    if store is None:
        await ctx.error("Vector store not available")
        return "Vector store not available. Index papers first."

    results = corpus_of(store, 1000)

    if not results:
        await ctx.info("No indexed papers found")
        return "No trending topics found. Index papers first."

    bigram_counter: Counter = Counter()
    bigram_titles: dict[str, list[str]] = {}

    for paper in results:
        title = paper.get("title", "")
        if not title:
            continue
        bigrams = _extract_bigrams(title, _STOPWORDS)
        for bg in bigrams:
            bigram_counter[bg] += 1
            if bg not in bigram_titles:
                bigram_titles[bg] = []
            if title not in bigram_titles[bg]:
                bigram_titles[bg].append(title)

    # Filter by minimum paper count and take top 10
    candidates = [
        (bg, count, bigram_titles[bg])
        for bg, count in bigram_counter.most_common()
        if count >= min_papers
    ]
    top_topics = candidates[:10]

    if not top_topics:
        await ctx.info("No trending topics met the minimum threshold")
        return "No trending topics found. Index papers first."

    lines = [
        "# Trending Research Topics\n",
        f"**Total papers analyzed:** {len(results)}\n",
        f"**Minimum papers per topic:** {min_papers}\n",
        "---\n",
    ]

    for i, (bigram, count, titles) in enumerate(top_topics, 1):
        lines.append(f"## {i}. \"{bigram.title()}\" ({count} papers)\n")
        for t in titles[:5]:
            lines.append(f"- {t}")
        if len(titles) > 5:
            lines.append(f"  *... and {len(titles) - 5} more papers*")
        lines.append("")

    await ctx.info(f"Found {len(top_topics)} trending topics from {len(results)} papers")
    return "\n".join(lines)
