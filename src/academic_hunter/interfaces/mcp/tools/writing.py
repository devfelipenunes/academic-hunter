"""MCP tools for scientific article authoring.

Division of labour: these tools assemble structure, real numbers and verified
context; the connected agent writes the prose. Nothing here calls an LLM, which
keeps the output free of fabricated figures and preserves the project's
offline, zero-cost character. See ``academic_hunter.core.writing``.
"""

import csv
import json
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import Context

from academic_hunter import __version__
from academic_hunter.core.writing import (
    ExistenceProbes,
    build_outline,
    extract_citations,
    format_bibtex_key,
    get_template,
    list_templates,
    parse_bibtex_entries,
    summarize_citations,
    verify_existence,
)
from academic_hunter.core.writing.outline import RunData
from academic_hunter.core.writing.numbers import (
    extract_claims,
    index_results,
    summarize_numbers,
    verify_numbers as check_numbers,
)
from ._utils import get_project_root, _get_vector_store
from ..exceptions import CitationError, WritingError


def _resolve_run_dir(project_root: Path, source_run: Optional[str]) -> Path:
    """Find the run directory to build an outline from.

    Accepts either a run name ("run_20260910_011631") or a path. Without an
    explicit choice, uses the most recent run.
    """
    results_dir = project_root / "results"

    if source_run:
        candidate = Path(source_run)
        if not candidate.is_absolute():
            candidate = results_dir / source_run
        if not candidate.is_dir():
            raise WritingError(
                f"Run not found: {source_run}",
                details={"looked_in": str(results_dir)},
            )
        return candidate

    runs = sorted(
        (d for d in results_dir.glob("run_*") if d.is_dir()),
        key=lambda d: d.name,
        reverse=True,
    )
    if not runs:
        raise WritingError(
            "No completed runs found. Execute run_search first.",
            details={"looked_in": str(results_dir)},
        )
    return runs[0]


def _load_run_data(run_dir: Path, topic: str) -> tuple[RunData, list[str]]:
    """Read a run's numbers and paper list.

    Returns the data plus a list of warnings about anything that could not be
    read. A run performed before ``run_stats_<ts>.json`` existed (added in 2.1.0)
    yields an outline without numbers rather than an error — the agent still gets
    the structure, and the warning says why the figures are missing.
    """
    warnings: list[str] = []

    stats: dict = {}
    stats_files = sorted(run_dir.glob("run_stats_*.json"))
    if stats_files:
        try:
            stats = json.loads(stats_files[-1].read_text())
        except (OSError, json.JSONDecodeError) as exc:
            warnings.append(f"Could not read {stats_files[-1].name}: {exc}")
    else:
        warnings.append(
            "No run_stats_*.json in this run — it predates structured run "
            "statistics, so the outline has no screening numbers. Re-run the "
            "search to get them."
        )

    papers: list[dict] = []
    csv_files = sorted(run_dir.glob("academic_dataset_*.csv"))
    if csv_files:
        try:
            with open(csv_files[-1], newline="", encoding="utf-8") as fh:
                papers = list(csv.DictReader(fh))
        except OSError as exc:
            warnings.append(f"Could not read {csv_files[-1].name}: {exc}")

    data = RunData(
        topic=topic or "",
        stats={
            "identified": stats.get("identified", {}),
            "duplicates_removed": stats.get("duplicates_removed", 0),
            "excluded_year": stats.get("excluded_year", 0),
            "excluded_anchors": stats.get("excluded_anchors", 0),
            "excluded_technical_score": stats.get("excluded_technical_score", 0),
            "included_final": stats.get("included_final", 0),
        } if stats else {},
        source_breakdown=stats.get("identified", {}),
        exclusions_by_source=stats.get("exclusions_by_source", {}),
        papers=papers,
        run_timestamp=stats.get("timestamp") or run_dir.name.removeprefix("run_"),
    )
    return data, warnings


async def outline_paper(
    ctx: Context,
    paper_type: str = "method",
    topic: str = "",
    source_run: str = None,
) -> str:
    """Build a scientific article skeleton from a completed search run.

    Produces the section structure for the chosen paper type, with every number
    filled in from the run's own data and explicit markers where the agent must
    write prose. No text is generated — this is structure and data only.

    After receiving the outline, write each marked section using `paper_context`
    to pull citable papers from the corpus, then run `verify_citations` over the
    result before considering it done.

    Args:
        ctx: FastMCP Context (auto-injected).
        paper_type: "method" (contribution paper), "software" (JOSS format) or
            "survey" (landscape mapping).
        topic: Article title/subject. Falls back to the run's anchors.
        source_run: Run directory name or path. Defaults to the most recent run.

    Returns:
        Markdown skeleton, ready to be filled by the agent.
    """
    available = ", ".join(t.key for t in list_templates())
    await ctx.info(f"Building '{paper_type}' outline (available: {available})")

    try:
        template = get_template(paper_type)
    except KeyError as exc:
        await ctx.error(str(exc))
        raise WritingError(str(exc), details={"available": available})

    try:
        project_root = get_project_root()
        run_dir = _resolve_run_dir(project_root, source_run)
        await ctx.info(f"Using run: {run_dir.name}")

        data, warnings = _load_run_data(run_dir, topic)
        for warning in warnings:
            await ctx.warning(warning)

        if not data.topic:
            # Fall back to the run's anchors so the title is never blank.
            anchors = _anchors_from(run_dir)
            data.topic = ", ".join(anchors) if anchors else run_dir.name

        outline = build_outline(template, data)

        n_sections = len(template.section_names())
        await ctx.info(
            f"Outline ready: {template.label}, {n_sections} sections, "
            f"~{template.total_words} words target"
        )
        header = (
            f"Outline generated: **{template.label}** "
            f"({n_sections} sections, ~{template.total_words} words) "
            f"from `{run_dir.name}`.\n\n"
        )
        if warnings:
            header += "Warnings:\n" + "\n".join(f"- {w}" for w in warnings) + "\n\n"
        return header + outline

    except WritingError:
        raise
    except Exception as exc:
        await ctx.error(f"Outline generation failed: {exc}")
        raise WritingError(str(exc))


def _anchors_from(run_dir: Path) -> list[str]:
    """Read anchor names from a run's stats file, for a fallback title."""
    stats_files = sorted(run_dir.glob("run_stats_*.json"))
    if not stats_files:
        return []
    try:
        return json.loads(stats_files[-1].read_text()).get("anchors", []) or []
    except (OSError, json.JSONDecodeError):
        return []


async def paper_context(
    ctx: Context,
    topic: str,
    section: str = "",
    top_k: int = 20,
) -> str:
    """Retrieve papers from the indexed corpus, formatted for citation.

    Use this before writing any section that needs references. The returned
    entries carry a ready-to-use citation key in the project's convention, so
    the agent cites real indexed papers instead of recalling them — the
    failure mode that produces fabricated references.

    After writing, run `verify_citations` to confirm every key actually exists.

    Args:
        ctx: FastMCP Context (auto-injected).
        topic: What the section is about.
        section: Section name (e.g. "Related Work"), to steer retrieval.
        top_k: How many papers to return (max 50).

    Returns:
        Formatted list of citable papers with keys, DOIs and abstracts.
    """
    store = _get_vector_store()
    if store is None:
        await ctx.error("Vector store not available")
        raise CitationError(
            "Vector store not available — index papers by running a search first."
        )

    query = f"{topic} {section}".strip() if section else topic
    top_k = min(max(top_k, 1), 50)
    await ctx.info(f"Retrieving up to {top_k} papers for: '{query}'")

    try:
        results = store.query(query, top_k=top_k)
    except Exception as exc:
        await ctx.error(f"Corpus query failed: {exc}")
        raise CitationError(str(exc))

    if not results:
        await ctx.info("No matching papers in the corpus")
        return (
            "No papers found in the corpus for this query. Either the corpus "
            "does not cover the topic, or no search has been indexed yet."
        )

    lines = [
        f"# Citable papers for: {topic}",
        "",
        f"{len(results)} papers retrieved from the indexed corpus. Use the "
        "`key` verbatim in `[@key]` citations — it matches the project's "
        "convention (`format_bibtex_key`).",
        "",
    ]

    for i, paper in enumerate(results, 1):
        title = str(paper.get("title", "")).strip()
        year = paper.get("year") or ""
        key = format_bibtex_key(title, year) if title else f"ref{i}"
        lines.append(f"## {i}. {title}")
        lines.append(f"- **key:** `{key}`")
        if year:
            lines.append(f"- **year:** {year}")
        if paper.get("venue"):
            lines.append(f"- **venue:** {paper['venue']}")
        if paper.get("doi"):
            lines.append(f"- **doi:** `{paper['doi']}`")
        if paper.get("source"):
            lines.append(f"- **source:** {paper['source']}")
        if paper.get("abstract"):
            abstract = " ".join(str(paper["abstract"]).split())
            lines.append(f"- **abstract:** {abstract[:400]}")
        lines.append("")

    return "\n".join(lines)


async def verify_citations(
    ctx: Context,
    text: str,
    bib_path: str = None,
) -> str:
    """Verify that every citation in a text points to a real reference.

    Runs layer 1 (existence) over all `[@key]` citations found. Three checks are
    attempted, each only when the information to answer it is available:

    - **bibliography** — is the key present in the given .bib file?
    - **DOI** — does the DOI recorded for that key resolve?
    - **corpus** — is the paper among the locally indexed ones?

    A citation is reported NOT_FOUND as soon as an available check fails, and
    UNKNOWN when no check could be made — "could not verify" is never reported as
    "fabricated", because those are different claims.

    Args:
        ctx: FastMCP Context (auto-injected).
        text: Manuscript text containing `[@key]` citations.
        bib_path: Path to the .bib file. Relative paths resolve against the
            project root. Without it, only the corpus check can run.

    Returns:
        Per-citation report with verdicts, plus a summary count.
    """
    candidates = extract_citations(text)
    if not candidates:
        await ctx.info("No [@key] citations found in the supplied text")
        return "No `[@key]` citations found. Nothing to verify."

    await ctx.info(f"Verifying {len(candidates)} citation(s)")

    entries: dict = {}
    if bib_path:
        bib_file = Path(bib_path)
        if not bib_file.is_absolute():
            bib_file = get_project_root() / bib_path
        if not bib_file.is_file():
            raise CitationError(f"Bibliography not found: {bib_path}")
        entries = parse_bibtex_entries(bib_file.read_text(encoding="utf-8"))
        await ctx.info(f"Loaded {len(entries)} bibliography entries")

    store = _get_vector_store()

    def in_bibliography(key: str):
        return key in entries if entries else None

    def resolve_doi(key: str):
        entry = entries.get(key) or {}
        return entry.get("doi") or None

    def doi_resolves(doi: str) -> Optional[bool]:
        """Refuting probe: `False` accuses, so only Crossref may say it.

        A 404 is the registry answering "no such DOI". Everything else — a
        timeout, a 429, a 5xx — is the registry declining to answer, and that is
        `None`: `verify_existence` reports it as unverifiable rather than
        fabricated. Returning `False` for those accused live references of being
        invented whenever Crossref had a bad minute.
        """
        import requests

        try:
            response = requests.get(
                f"https://api.crossref.org/works/{doi}",
                timeout=10,
                headers={"User-Agent": f"AcademicHunter/{__version__} (citation check)"},
            )
        except requests.RequestException:
            return None

        if response.status_code == 200:
            return True
        if response.status_code == 404:
            return False
        return None

    def in_corpus(key: str):
        """Confirming probe: is this cited work among the locally indexed papers?

        Searches by the entry's title, not by its key — the key is a local label
        and carries no retrievable meaning, so querying with it returns noise.
        A miss is not a defect (see ExistenceProbes): the corpus is a subset.
        """
        if store is None:
            return None
        title = ((entries.get(key) or {}).get("title") or "").strip()
        if not title:
            return None
        try:
            hits = store.query(title, top_k=3)
        except Exception:
            return None
        needle = title[:40].lower()
        for hit in hits:
            candidate_title = str(hit.get("title", "")).lower()
            if candidate_title and (
                needle in candidate_title or candidate_title[:40] in title.lower()
            ):
                return True
        return False

    probes = ExistenceProbes(
        in_bibliography=in_bibliography,
        resolve_doi=resolve_doi if entries else None,
        doi_resolves=doi_resolves if entries else None,
        in_corpus=in_corpus,
    )

    results = verify_existence(candidates, probes)
    counts = summarize_citations(results)

    lines = [
        "# Citation verification (layer 1 — existence)",
        "",
        f"Checked {len(results)} citation(s): "
        f"**{counts['VERIFIED']} verified**, "
        f"**{counts['NOT_FOUND']} not found**, "
        f"{counts['UNKNOWN']} unverifiable.",
        "",
    ]

    if counts["NOT_FOUND"]:
        lines.append("## Not found")
        lines.append("")
        for r in results:
            if r.verdict == "NOT_FOUND":
                lines.append(f"- `{r.key}` — {r.evidence}")
                if r.context:
                    lines.append(f"  - used in: _{r.context[:200]}_")
        lines.append("")

    if counts["UNKNOWN"]:
        lines.append("## Unverifiable (no evidence either way)")
        lines.append("")
        for r in results:
            if r.verdict == "UNKNOWN":
                lines.append(f"- `{r.key}` — {r.evidence}")
        lines.append("")

    if counts["VERIFIED"]:
        lines.append("## Verified")
        lines.append("")
        for r in results:
            if r.verdict == "VERIFIED":
                lines.append(f"- `{r.key}` — {r.evidence}")
        lines.append("")

    return "\n".join(lines)


async def verify_numbers(
    ctx: Context,
    text: str,
    results_dir: str = None,
) -> str:
    """Check the figures in a text against the experiment result files.

    Extracts every checkable number from the text — percentages, correlations,
    p-values, counts of papers — and confronts each with the values actually
    present in the result JSONs.

    A figure reported UNSOURCED has no counterpart in those files. That is a
    prompt to look, not a verdict that the number is wrong: manuscripts
    legitimately quote figures from cited literature, which is not in the result
    files. The report names the files searched so the two cases can be told
    apart.

    Args:
        ctx: FastMCP Context (auto-injected).
        text: Manuscript text to check.
        results_dir: Directory of result files. Defaults to ``results/`` in the
            project — the directory the pipeline writes its runs into.

    Returns:
        Per-figure report with statuses, plus a summary count.
    """
    claims = extract_claims(text)
    if not claims:
        await ctx.info("No checkable figures found in the supplied text")
        return "No checkable figures found. Nothing to verify."

    project_root = get_project_root()
    results_path = Path(results_dir) if results_dir else project_root / "results"
    if not results_path.is_absolute():
        results_path = project_root / results_path

    await ctx.info(f"Checking {len(claims)} figures against {results_path}")

    known = index_results(results_path)
    if not known:
        await ctx.warning(
            f"No numbers indexed from {results_path} — cannot confirm any figure."
        )

    results = check_numbers(claims, known)
    counts = summarize_numbers(results)

    lines = [
        "# Figure verification (layer 3 — against result files)",
        "",
        f"Checked {len(results)} figure(s): "
        f"**{counts['MATCHED']} matched**, "
        f"**{counts['CLOSE']} close**, "
        f"**{counts['UNSOURCED']} unsourced**.",
        "",
        f"Source: `{results_path}` ({len(known)} distinct values indexed).",
        "",
    ]

    if counts["UNSOURCED"]:
        lines.append("## Unsourced — no matching value in the result files")
        lines.append("")
        lines.append(
            "_Not necessarily wrong: figures quoted from cited literature will "
            "also land here. Confirm each one has a real source._"
        )
        lines.append("")
        for r in results:
            if r.status == "UNSOURCED":
                lines.append(f"- `{r.claim.raw}` ({r.claim.kind})")
                if r.claim.context:
                    lines.append(f"  - in: _{r.claim.context[:200]}_")
        lines.append("")

    if counts["CLOSE"]:
        lines.append("## Close — matched within rounding tolerance")
        lines.append("")
        for r in results:
            if r.status == "CLOSE":
                lines.append(
                    f"- `{r.claim.raw}` ≈ {r.matched_value} ({r.claim.kind})"
                )
        lines.append("")

    if counts["MATCHED"]:
        lines.append("## Matched")
        lines.append("")
        for r in results:
            if r.status == "MATCHED":
                lines.append(f"- `{r.claim.raw}` = {r.matched_value} ({r.claim.kind})")
        lines.append("")

    return "\n".join(lines)
