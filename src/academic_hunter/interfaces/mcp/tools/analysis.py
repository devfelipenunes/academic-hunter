"""MCP tools for paper analysis — trending topics, paper comparison, and report export.

All tools accept a ``ctx: Context`` parameter (auto-injected by FastMCP)
for logging and progress reporting.
"""

import json
import logging
import os
import requests
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import Context

from academic_hunter import AcademicHunter
from academic_hunter.plugins.vector_stores import ChromaVectorStore
from ._utils import get_project_root
from ..exceptions import DiscoveryError, SearchError

logger = logging.getLogger("academic_hunter.mcp.analysis")

_STOPWORDS = {
    "the", "a", "an", "of", "in", "for", "and", "or", "to", "with",
    "on", "at", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "but",
    "not", "what", "which", "who", "whom", "this", "that", "these",
    "those", "it", "its", "study", "research", "paper", "approach",
    "method", "result", "analysis", "based", "using", "new", "novel",
}


def _get_vector_store():
    """Initialize the ChromaDB vector store (same pattern as rag.py)."""
    try:
        hunter = AcademicHunter(output_dir=str(get_project_root() / "results"))
        db_dir = str(hunter.output_dir.parent / ".academic_hunter" / "chroma_db")
        return ChromaVectorStore(db_dir=db_dir)
    except Exception:
        return None


def _extract_bigrams(title: str, stopwords: set) -> list[str]:
    """Extract meaningful bigrams from a title, excluding stopwords."""
    import re

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

    # Retrieve all indexed papers via a broad query with a high limit.
    # ChromaDB will clamp n_results to the collection size.
    results = store.query("research paper topic analysis", top_k=1000)

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


async def compare_papers(ctx: Context, doi_a: str, doi_b: str) -> str:
    """Compares two papers side by side using Semantic Scholar metadata.

    Fetches title, year, and abstract for both DOIs, computes shared keywords
    from their abstracts, and presents a formatted comparison.

    Args:
        ctx: FastMCP Context (auto-injected).
        doi_a: DOI of the first paper.
        doi_b: DOI of the second paper.
    """
    await ctx.info(f"Comparing papers: {doi_a} vs {doi_b}")

    try:
        def _fetch_meta(doi: str) -> dict:
            """Fetch paper metadata — tries Semantic Scholar, falls back to AcademicHunter."""
            last_error = None
            # Try Semantic Scholar API
            try:
                url = (
                    f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
                    "?fields=title,year,abstract"
                )
                resp = requests.get(url, timeout=10)
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as e:
                last_error = e

            # Fallback: arXiv DOIs (10.48550/arXiv.xxxx) not found by Semantic Scholar
            try:
                hunter = AcademicHunter()
                abstract = hunter.fetch_abstract_by_doi(doi)
                if abstract:
                    title = abstract.strip().split("\n")[0][:80] if abstract else doi
                    return {"title": title, "year": None, "abstract": abstract}
            except Exception as e:
                last_error = e

            # Both attempts failed — re-raise the original error
            raise DiscoveryError(str(last_error)) if last_error else DiscoveryError(f"Paper {doi} not found")

        def _keyword_set(text: str) -> set[str]:
            """Extract meaningful keywords from text."""
            import re

            words = re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", text.lower())
            return {w for w in words if w not in _STOPWORDS}

        # Fetch metadata for both papers
        meta_a = _fetch_meta(doi_a)
        meta_b = _fetch_meta(doi_b)

        hunter = AcademicHunter()

        title_a = meta_a.get("title") or "Unknown Title"
        title_b = meta_b.get("title") or "Unknown Title"
        year_a = meta_a.get("year") or "Unknown Year"
        year_b = meta_b.get("year") or "Unknown Year"

        abstract_a = meta_a.get("abstract") or ""
        if not abstract_a:
            abstract_a = hunter.fetch_abstract_by_doi(doi_a) or ""

        abstract_b = meta_b.get("abstract") or ""
        if not abstract_b:
            abstract_b = hunter.fetch_abstract_by_doi(doi_b) or ""

        # Compute shared keywords
        kw_a = _keyword_set(abstract_a)
        kw_b = _keyword_set(abstract_b)
        shared = sorted(kw_a & kw_b)

        # Format abstract previews (first 400 chars)
        preview_a = (abstract_a[:400] + "...") if len(abstract_a) > 400 else (abstract_a or "*Not found*")
        preview_b = (abstract_b[:400] + "...") if len(abstract_b) > 400 else (abstract_b or "*Not found*")

        lines = [
            "# Paper Comparison\n",
            "| Field | Paper A | Paper B |",
            "|-------|---------|---------|",
            f"| **DOI** | `{doi_a}` | `{doi_b}` |",
            f"| **Title** | {title_a} | {title_b} |",
            f"| **Year** | {year_a} | {year_b} |",
            "",
            "## Abstract Preview — Paper A",
            preview_a,
            "",
            "## Abstract Preview — Paper B",
            preview_b,
            "",
        ]

        if shared:
            lines.append(f"## Shared Keywords ({len(shared)})")
            lines.append(", ".join(shared))
        else:
            lines.append("## Shared Keywords")
            lines.append("*No significant keyword overlap found.*")

        lines.append("")
        await ctx.info("Comparison complete")
        return "\n".join(lines)

    except DiscoveryError:
        await ctx.error("Failed to compare papers")
        raise
    except Exception as e:
        await ctx.error(f"Failed to compare papers: {e}")
        raise DiscoveryError(str(e))


async def export_report(
    ctx: Context, format: str = "csv", output_path: Optional[str] = None
) -> str:
    """Exports the latest consolidated search results in CSV, JSON, BibTeX, or RIS format.

    Args:
        ctx: FastMCP Context (auto-injected).
        format: Export format — ``"csv"`` (default), ``"json"``, ``"bibtex"``, or ``"ris"``.
        output_path: Full path for the output file.  If omitted, the file is
                     written to ``results/export_{timestamp}.{ext}``.
    """
    await ctx.info(f"Exporting report in {format} format")

    try:
        project_root = get_project_root()
        hunter = AcademicHunter(output_dir=str(project_root / "results"))
        papers = list(hunter.consolidated_results.values())

        # Fallback: load from latest CSV when no in-memory results
        if not papers:
            await ctx.info("No in-memory results, trying latest CSV...")
            results_dir = project_root / "results"
            csv_files = sorted(
                results_dir.glob("academic_dataset_*.csv"),
                key=os.path.getctime,
                reverse=True,
            )
            if csv_files:
                import pandas as pd
                df = pd.read_csv(csv_files[0])
                papers = df.to_dict(orient="records")
                await ctx.info(f"Loaded {len(papers)} papers from {csv_files[0].name}")

        if not papers:
            await ctx.info("No search results to export")
            return "No search results to export."

        format_lower = format.lower()
        supported_formats = ("csv", "json", "bibtex", "ris")
        if format_lower not in supported_formats:
            await ctx.error(f"Unsupported format: {format}")
            return "Unsupported format. Use 'csv', 'json', 'bibtex', or 'ris'."

        ext_map = {"csv": "csv", "json": "json", "bibtex": "bib", "ris": "ris"}
        ext = ext_map[format_lower]

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_dir = project_root / "results"
        results_dir.mkdir(parents=True, exist_ok=True)

        if output_path is None:
            output_path = str(results_dir / f"export_{timestamp}.{ext}")

        if format_lower == "csv":
            import pandas as pd  # lazy import

            df = pd.DataFrame(papers)
            df.to_csv(output_path, index=False)

        elif format_lower == "json":
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(papers, f, indent=2, ensure_ascii=False, default=str)

        elif format_lower == "bibtex":
            _write_bibtex(papers, output_path)

        elif format_lower == "ris":
            _write_ris(papers, output_path)

        await ctx.info(f"Exported {len(papers)} papers to {output_path}")
        return f"Successfully exported {len(papers)} papers to {output_path}"

    except SearchError:
        raise
    except Exception as e:
        await ctx.error(f"Failed to export report: {e}")
        raise SearchError(str(e))


def _write_bibtex(papers: list, output_path: str) -> None:
    """Write papers to a BibTeX file.

    Each paper produces an ``@article{...}`` entry with author, title,
    journal, year, url, doi, and abstract fields where available.
    """
    lines = []
    for i, paper in enumerate(papers):
        doi = paper.get("DOI", "")
        key = doi.replace("/", "-").replace("_", "-") if doi else f"paper_{i + 1}"

        authors = paper.get("Authors", paper.get("author", ""))
        if isinstance(authors, list):
            authors = " and ".join(authors)

        title = paper.get("Title", "")
        journal = paper.get("Source", "")
        year = paper.get("Year", "")
        url = paper.get("URL", "")
        abstract = paper.get("Abstract", "")

        lines.append(f"@article{{{key},")
        if authors:
            lines.append(f"  author = {{{authors}}},")
        if title:
            lines.append(f"  title = {{{title}}},")
        if journal:
            lines.append(f"  journal = {{{journal}}},")
        if year:
            lines.append(f"  year = {{{year}}},")
        if url:
            lines.append(f"  url = {{{url}}},")
        if doi:
            lines.append(f"  doi = {{{doi}}},")
        if abstract:
            lines.append(f"  abstract = {{{abstract}}},")
        lines.append("}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _write_ris(papers: list, output_path: str) -> None:
    """Write papers to a RIS file.

    Each paper produces a RIS record with fields for type (JOUR),
    title (TI), authors (AU), year (PY), journal (JO), DOI (DO),
    abstract (AB), and URL (UR).
    """
    records = []
    for paper in papers:
        entry = ["TY  - JOUR"]

        title = paper.get("Title", "")
        if title:
            entry.append(f"TI  - {title}")

        authors = paper.get("Authors", paper.get("author", ""))
        if isinstance(authors, list):
            for a in authors:
                entry.append(f"AU  - {a}")
        elif authors:
            entry.append(f"AU  - {authors}")

        year = paper.get("Year", "")
        if year:
            entry.append(f"PY  - {year}")

        journal = paper.get("Source", "")
        if journal:
            entry.append(f"JO  - {journal}")

        doi = paper.get("DOI", "")
        if doi:
            entry.append(f"DO  - {doi}")

        abstract = paper.get("Abstract", "")
        if abstract:
            entry.append(f"AB  - {abstract}")

        url = paper.get("URL", "")
        if url:
            entry.append(f"UR  - {url}")

        entry.append("ER  - ")
        records.append("\n".join(entry))

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(records) + "\n")


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


async def find_related_papers(ctx: Context, query: str, top_k: int = 5) -> str:
    """Finds papers semantically similar to a given query.

    Args:
        ctx: FastMCP Context (auto-injected).
        query: Search text (title, DOI, or free text).
        top_k: Number of results (default 5, max 20).
    """
    await ctx.info(f"Finding papers related to: '{query[:60]}'...")
    store = _get_vector_store()
    if store is None:
        await ctx.error("Vector store not available")
        return "Vector store not available. Index papers first."

    top_k = min(top_k, 20)
    results = store.query(query, top_k=top_k)
    if not results:
        await ctx.info("No related papers found")
        return "No related papers found. Try a different query."

    lines = ["# Related Papers\n", f"**Query:** {query}\n",
             f"**Results:** {len(results)}\n", "---\n"]
    for i, paper in enumerate(results, 1):
        title = paper.get("title", "Untitled")
        rel = paper.get("semantic_relevance", 0)
        year = paper.get("year", "?")
        doi = paper.get("doi", "")
        preview = paper.get("abstract_preview", "")
        lines.append(f"## {i}. {title}\n")
        lines.append(f"- **Relevance:** {rel:.1%} | **Year:** {year}\n")
        if doi: lines.append(f"- **DOI:** `{doi}`\n")
        if preview: lines.append(f"{preview[:200]}...\n")
        lines.append("")
    await ctx.info(f"Found {len(results)} related papers")
    return "\n".join(lines)


# ── summarization ──────────────────────────────────────────────────────────────


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
        hunter = AcademicHunter()
        abstract = hunter.fetch_abstract_by_doi(doi)
    except Exception as e:
        await ctx.error(f"Failed to fetch paper: {e}")
        return f"Could not fetch paper with DOI {doi}."

    if not abstract or len(abstract.strip()) < 50:
        await ctx.info(f"Abstract too short or not found for {doi}")
        return f"Abstract too short or not available for DOI {doi}."

    num_sentences = min(num_sentences, 8)

    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np

        # Split into sentences
        import re
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', abstract) if len(s.strip()) > 20]
        if len(sentences) <= num_sentences:
            await ctx.info("Abstract has fewer sentences than requested")
            return f"# Abstract Summary\n\n{abstract}"

        # Embed sentences
        model = SentenceTransformer("all-MiniLM-L6-v2")
        emb = model.encode(sentences)

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
        lines = [f"# Extractive Summary\n", f"**DOI:** {doi}\n",
                 f"**Method:** Centroid + MMR (MiniLM)\n", f"**Sentences:** {num_sentences}\n", "---\n"]
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
