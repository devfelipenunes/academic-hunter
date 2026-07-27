"""MCP tool for novelty/outlier paper detection using EllipticEnvelope.

Accepts a ``ctx: Context`` parameter (auto-injected by FastMCP)
for logging and progress reporting.
"""

import logging

from mcp.server.fastmcp import Context

from ._utils import _get_vector_store

logger = logging.getLogger("academic_hunter.mcp.novelty")


async def find_novel_papers(ctx: Context, top_k: int = 500, contamination: float = 0.1) -> str:
    """Finds novel/outlier papers that don't fit the main research themes.

    Uses EllipticEnvelope over MiniLM embeddings to detect papers whose content
    is significantly different from the corpus centroid.

    Args:
        ctx: FastMCP Context (auto-injected).
        top_k: Number of papers to analyze (default 500).
        contamination: Expected proportion of outliers (default 0.1).
    """
    await ctx.info(f"Running novelty detection on {top_k} papers...")
    store = _get_vector_store()
    if store is None:
        await ctx.error("Vector store not available")
        return "Vector store not available. Index papers first."

    results = store.query("research novelty outlier detection", top_k=top_k)
    if not results or len(results) < 5:
        await ctx.info("Too few papers for novelty detection")
        return "Not enough papers for novelty detection."

    try:
        from sentence_transformers import SentenceTransformer
        from sklearn.covariance import EllipticEnvelope

        model = SentenceTransformer("all-MiniLM-L6-v2")
        texts = [f"{p.get('title', '')} {p.get('abstract', '')}" for p in results]
        embeddings = model.encode(texts)

        detector = EllipticEnvelope(contamination=contamination, random_state=42)
        predictions = detector.fit_predict(embeddings)
        scores = detector.decision_function(embeddings)

        outliers = [(i, scores[i]) for i, pred in enumerate(predictions) if pred == -1]
        outliers.sort(key=lambda x: x[1])

        if not outliers:
            await ctx.info("No outlier papers detected")
            return "# Novelty Detection\n\nNo outlier papers detected."

        lines = ["# Novel/Outlier Papers\n",
                 f"**Papers analyzed:** {len(results)}\n",
                 f"**Outliers found:** {len(outliers)}\n", "---\n"]
        for idx, score in outliers[:10]:
            paper = results[idx]
            lines.append(f"## {paper.get('title', 'Untitled')} ({paper.get('year', '?')})\n")
            lines.append(f"- **Anomaly score:** {score:.4f}\n")
            if paper.get("abstract_preview"):
                lines.append(f"- **Preview:** {paper['abstract_preview'][:200]}...\n")
            lines.append("")
        await ctx.info(f"Found {len(outliers)} outlier papers")
        return "\n".join(lines)
    except ImportError as e:
        await ctx.error(f"Missing dependency: {e}")
        return f"Required library not installed: {e}"
    except Exception as e:
        await ctx.error(f"Novelty detection failed: {e}")
        return f"Novelty detection failed: {e}"
