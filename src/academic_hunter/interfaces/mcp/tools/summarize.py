"""MCP tool for extractive paper summarization (centroid + MMR).

Accepts a ``ctx: Context`` parameter (auto-injected by FastMCP)
for logging and progress reporting.
"""

import logging
import re

from academic_hunter import AcademicHunter
from academic_hunter.core.nlp.model_cache import get_sentence_transformer
from mcp.server.fastmcp import Context

from ..validation import validate_doi
from ._utils import run_blocking

logger = logging.getLogger("academic_hunter.mcp.summarize")


async def summarize_paper(ctx: Context, doi: str, num_sentences: int = 3) -> str:
    """Generates an extractive summary of a paper's abstract.

    Uses MiniLM embeddings + Maximal Marginal Relevance (MMR) to select
    the most representative and non-redundant sentences.

    Args:
        ctx: FastMCP Context (auto-injected).
        doi: DOI of the paper to summarize.
        num_sentences: Number of sentences in the summary (default 3, max 8).
    """
    await ctx.info(f"Summarizing paper DOI {doi}...")

    # Fetch abstract
    try:
        doi = validate_doi(doi)
        hunter = await run_blocking(AcademicHunter)
        abstract = hunter.fetch_abstract_by_doi(doi)
    except ValueError as e:
        await ctx.error(f"Invalid DOI: {e}")
        return f"Invalid DOI: {e}"
    except Exception as e:
        await ctx.error(f"Failed to fetch paper: {e}")
        return f"Could not fetch paper with DOI {doi}."

    if not abstract or len(abstract.strip()) < 50:
        await ctx.info(f"Abstract too short or not found for {doi}")
        return f"Abstract too short or not available for DOI {doi}."

    num_sentences = min(num_sentences, 8)

    try:
        import numpy as np

        # Split into sentences
        sentences = [
            s.strip()
            for s in re.split(r'(?<=[.!?])\s+', abstract)
            if len(s.strip()) > 20
        ]
        if len(sentences) <= num_sentences:
            await ctx.info("Abstract has fewer sentences than requested")
            return f"# Abstract Summary\n\n{abstract}"

        # Embed sentences. The model comes from the shared cache — loading
        # MiniLM takes seconds and this tool used to pay it on every call.
        # Raising ImportError keeps the existing handler's message intact.
        model = await run_blocking(get_sentence_transformer)
        if model is None:
            raise ImportError("sentence-transformers")
        emb = await run_blocking(model.encode, sentences)

        # Centroid
        centroid = np.mean(emb, axis=0)

        # MMR selection
        selected = []
        remaining = list(range(len(sentences)))

        # First pick: closest to centroid
        sims = emb @ centroid / (np.linalg.norm(emb, axis=1) * np.linalg.norm(centroid) + 1e-10)
        first = int(np.argmax(sims))
        selected.append(first)
        remaining.remove(first)

        # Subsequent picks: MMR
        lambda_param = 0.7
        for _ in range(min(num_sentences - 1, len(remaining))):
            mmr_scores = []
            for i in remaining:
                # Relevance to centroid
                rel = float(emb[i] @ centroid / (np.linalg.norm(emb[i]) * np.linalg.norm(centroid) + 1e-10))
                # Diversity: max similarity to already selected
                sim_to_sel = max(float(emb[i] @ emb[j] / (np.linalg.norm(emb[i]) * np.linalg.norm(emb[j]) + 1e-10)) for j in selected)
                mmr = lambda_param * rel - (1 - lambda_param) * sim_to_sel
                mmr_scores.append((i, mmr))
            best = max(mmr_scores, key=lambda x: x[1])[0]
            selected.append(best)
            remaining.remove(best)

        selected.sort()
        lines = ["# Extractive Summary\n", f"**DOI:** {doi}\n",
                 "**Method:** Centroid + MMR (MiniLM)\n", f"**Sentences:** {num_sentences}\n", "---\n"]
        for i, idx in enumerate(selected, 1):
            lines.append(f"**{i}.** {sentences[idx]}\n\n")

        await ctx.info(f"Summary generated ({num_sentences} sentences)")
        return "\n".join(lines)

    except ImportError as e:
        await ctx.error(f"Missing dependency: {e}")
        return f"Required library not installed: {e}"
    except Exception as e:
        await ctx.error(f"Summarization failed: {e}")
        return f"Summarization failed: {e}"
