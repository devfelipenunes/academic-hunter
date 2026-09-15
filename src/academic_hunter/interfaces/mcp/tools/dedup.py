"""MCP tool for semantic deduplication of papers.

Uses MiniLM embeddings to find near-duplicate papers.
"""

import logging

import numpy as np

from academic_hunter.core.nlp.model_cache import get_sentence_transformer
from mcp.server.fastmcp import Context

from ._utils import _get_vector_store, corpus_of, run_blocking

logger = logging.getLogger("academic_hunter.mcp.dedup")


async def semantic_dedup(ctx: Context, threshold: float = 0.85, min_group_size: int = 2) -> str:
    """Finds near-duplicate papers using embedding similarity.

    Papers with cosine similarity above the threshold are grouped as
    potential duplicates. Uses MiniLM embeddings from the vector store.

    Args:
        ctx: FastMCP Context (auto-injected).
        threshold: Cosine similarity threshold (default 0.85).
        min_group_size: Minimum papers to form a group (default 2).
    """
    await ctx.info(f"Running semantic dedup (threshold={threshold})...")

    # Get vector store
    store = _get_vector_store()
    if store is None:
        await ctx.error("Vector store not available")
        return "Error: Vector store not available. Index papers first."

    results = corpus_of(store, 1000)
    if not results or len(results) < min_group_size:
        await ctx.info("Too few papers for dedup")
        return "Not enough papers for deduplication."

    # Compute embeddings for all papers. The model is shared and cached —
    # loading MiniLM takes seconds and this tool used to pay it on every call.
    model = await run_blocking(get_sentence_transformer)
    if model is None:
        await ctx.error("sentence-transformers not installed")
        return "Error: sentence-transformers not installed."

    try:
        texts = [f"{p.get('title', '')} {p.get('abstract_preview', '')}" for p in results]
        embeddings = await run_blocking(model.encode, texts)
    except Exception as e:
        await ctx.error(f"Embedding failed: {e}")
        return f"Error: embedding computation failed: {e}"

    # Compute pairwise cosine similarity efficiently
    norm = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
    sim_matrix = np.dot(norm, norm.T)

    # Find duplicate groups
    visited = set()
    groups = []
    for i in range(len(results)):
        if i in visited:
            continue
        group = [i]
        for j in range(i + 1, len(results)):
            if j in visited:
                continue
            if sim_matrix[i][j] >= threshold:
                group.append(j)
                visited.add(j)
        if len(group) >= min_group_size:
            visited.add(i)
            groups.append(group)

    if not groups:
        await ctx.info(f"No duplicates found (threshold={threshold})")
        return f"# Semantic Dedup\n\nNo duplicate groups found above threshold {threshold}."

    lines = [
        "# Semantic Dedup Results\n",
        f"**Papers analyzed:** {len(results)}\n",
        f"**Duplicate groups:** {len(groups)}\n",
        f"**Threshold:** {threshold}\n",
        "---\n",
    ]

    for g_idx, group in enumerate(groups, 1):
        lines.append(f"## Group {g_idx} ({len(group)} papers)\n")
        for idx in group:
            p = results[idx]
            title = p.get("title", "Untitled")
            doi = p.get("doi", "?")
            score = sim_matrix[group[0]][idx]
            lines.append(f"- {title} (DOI: `{doi}`, sim: {score:.2%})\n")
        lines.append("")

    await ctx.info(f"Found {len(groups)} duplicate groups")
    return "\n".join(lines)
