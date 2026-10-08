"""MCP tools for executing the academic search pipeline and reading results.

``run_search`` reports progress through the FastMCP Context when available.
"""

from academic_hunter import AcademicHunter
from academic_hunter.core.infra import paths
from mcp.server.fastmcp import Context

from ..exceptions import SearchError
from ._utils import _latest_report_path, get_project_root, run_blocking


def _coverage(hunter) -> str:
    """Which sources were actually queried this run, and what each returned.

    A source the pipeline skipped and a source that was queried and found
    nothing both read as 0 everywhere else. They are not the same thing, and
    without this the agent has no way to tell them apart.

    A source that needs a credential it does not have is the third case, and it
    reports 0 like the rest. It is named with its reason here, because "no API
    key" is something the caller can fix and "0" is not. Those are known before
    the run starts, so ``unavailable_sources`` names them.

    A source that is throttled mid-run is the fourth, and it is the one that
    cannot be known in advance. ``blocked_sources`` holds its domain, and it is
    the only place that says so: the query is recorded in the history *before*
    the request is sent, so a source that answered nothing after its first 429
    is indistinguishable from one that answered and found nothing -- unless the
    history is checked against the blocked set, which is what happens here.

    ``Identified: 11 | Included: 0`` reads as an empty field, and it is the
    moment the agent needs to hear otherwise: when nothing reaches the scorer,
    the anchors are what failed, and that is a thing the caller can fix.

    A degraded embedding is the other number that looks like a finding and is
    not. The pipeline logs it at the end of the run, which the agent never
    reads, so a run scored on keywords alone arrives looking like any other.
    """
    queried = {item.get("Source") for item in hunter.query_history}
    identified = hunter.stats.get("identified", {})
    unavailable = hunter.stats.get("unavailable_sources", {})
    blocked_domains = getattr(hunter, "blocked_sources", None) or set()
    blocked = {
        name
        for name, connector in hunter.connectors.items()
        if getattr(connector, "domain", "") in blocked_domains
    }
    grid = [
        name for name, connector in hunter.connectors.items() if not getattr(connector, "is_keyword_only", False)
    ]

    lines = ["", "Coverage by source:"]
    skipped = []
    for name, count in identified.items():
        if name in unavailable:
            lines.append(f"  {name}: NOT QUERIED")
        elif name in blocked:
            lines.append(f"  {name}: {count} (BLOCKED)")
        elif name in queried:
            lines.append(f"  {name}: {count}")
        else:
            lines.append(f"  {name}: NOT QUERIED")
            skipped.append(name)
    identified_total = sum(identified.values())
    included = hunter.stats.get("included_final", 0)
    lines.append(f"Identified: {identified_total} | Included: {included}")

    if unavailable:
        named = "; ".join(f"{name}: {reason}" for name, reason in unavailable.items())
        lines.append(
            f"These sources did not run, so their zeros above are not findings "
            f"-- {named}"
        )

    if blocked:
        lines.append(
            f"{', '.join(sorted(blocked))} started answering and then blocked "
            "itself after a rate limit, so the counts above are a floor and not a "
            "total. A query is recorded before its request is sent, so a source "
            "that stopped answering still appears in the history above. Add the "
            "key it wants, or lower limit_per_query to send it fewer requests -- "
            "the block lasts for this run only."
        )

    dropped_at_anchor = hunter.stats.get("excluded_anchors", 0)
    if (
        identified_total
        and not included
        and dropped_at_anchor
        and not hunter.stats.get("excluded_technical_score", 0)
    ):
        anchors = [term for group in hunter.config.anchors.values() for term in group]
        lines.append(
            f"Nothing reached the scorer: {dropped_at_anchor} of the "
            f"{identified_total} identified papers were dropped at the anchor "
            f"gate, whose terms are {', '.join(anchors)}, and none were dropped "
            "for a low score. An anchor matches as a whole phrase, so a "
            "multi-word anchor fires only on a title or abstract carrying it "
            "verbatim. This run is a statement about the anchors and not about "
            "the field -- widen them with update_config and run the search again."
        )

    if skipped and not hunter.config.tech_strings:
        lines.append(
            f"{', '.join(skipped)} never ran a query, so their zeros are not "
            "findings. Every source except the keyword-only ones is queried once "
            "per anchor x technical string, and technical_strings is empty. Add "
            f"it ({', '.join(grid)}) with update_config and run the search again."
        )
    elif skipped:
        lines.append(
            f"{', '.join(skipped)} never ran a query, so their zeros are not "
            "findings. They were skipped with a non-empty technical_strings, so "
            "something else stopped them -- the server log says what."
        )

    screener = getattr(hunter, "semantic_screener", None)
    if screener is not None and getattr(screener, "degraded", False):
        lines.append(
            "Semantic scoring was degraded: the embedding model did not load, so "
            "every semantic score in this run is 0.0 and the ranking is "
            "keyword-only. These numbers are not comparable to a run with a "
            "working model, and the model is a one-time 79 MB download."
        )

    fusion = (hunter.stats or {}).get("fusion") or {}
    discarded = fusion.get("discarded") or []
    if discarded:
        weights = fusion.get("weights", {})
        lines.append(
            f"Computed and then weighted 0: {', '.join(discarded)}. Every paper "
            "was scored on those signals and the ranking used none of them "
            f"(weights: {weights}), so this run's ordering is not comparable to "
            "one that fused. A weight is a decision about the corpus, and it is "
            "taken deliberately, not by omission."
        )
    return "\n".join(lines)


async def run_search(ctx: Context, limit_per_source: int = None) -> str:
    """Executes the consolidated academic search based on the keywords and weights from config.json.

    Run this after update_config. It refuses a config with no anchors, because
    the pipeline queries once per anchor and nothing would be asked.

    The reply lists every source with what it returned, marking the ones that
    were never queried -- a skipped source reports 0 just like a source that was
    asked and found nothing, and only this tells them apart.

    Args:
        ctx: FastMCP Context (auto-injected).
        limit_per_source: Max results per API source (default: from config).
    """
    await ctx.info("Starting academic search pipeline...")
    await ctx.report_progress(0, 3, "Initializing hunter")
    try:
        output_dir = str(get_project_root() / paths.RESULTS_DIRNAME)
        hunter = await run_blocking(AcademicHunter, output_dir=output_dir)

        if not hunter.config.is_scorable():
            raise SearchError(
                f"The configuration at '{hunter.config.config_path}' "
                f"(chosen by: {hunter.config.config_origin}) has no anchors, and "
                "the pipeline queries once per anchor across every source, so "
                "nothing would be asked. Set them with update_config, or point "
                "ACADEMIC_HUNTER_CONFIG at a config that has them."
            )

        if limit_per_source is None:
            limit_per_source = hunter.config.settings.get("limit_per_query", 100)

        await ctx.report_progress(1, 3, f"Querying academic APIs (limit={limit_per_source})")
        report_path = await run_blocking(hunter.run, limit_per_source=limit_per_source)

        await ctx.report_progress(2, 3, "Finalizing report")
        await ctx.info(f"Search completed. Report at: {report_path}")
        await ctx.report_progress(3, 3, "Complete")

        return f"Search completed successfully. Report generated at: {report_path}\n" + _coverage(hunter)
    except SearchError:
        raise
    except Exception as e:
        await ctx.error(f"Search failed: {e}")
        raise SearchError(str(e))


async def read_latest_report(ctx: Context, max_chars: int = 10000, offset: int = 0) -> str:
    """Reads the latest Markdown report generated in the results/ folder.

    Useful for the agent to summarize the findings right after running run_search().

    Args:
        ctx: FastMCP Context (auto-injected).
        max_chars: Maximum number of characters to return (default 10000).
        offset: Character offset to start reading from (default 0).
    """
    await ctx.info("Reading latest report...")
    try:
        results_dir = get_project_root() / paths.RESULTS_DIRNAME
        if not results_dir.exists():
            await ctx.info("No results directory found")
            raise SearchError("No results directory found. Have you run a search yet?")

        latest_file = _latest_report_path(results_dir)
        if latest_file is None:
            await ctx.info("No markdown reports found in results/")
            raise SearchError("No markdown reports found in results/.")
        with open(latest_file, encoding="utf-8") as f:
            content = f.read()

        if offset > 0:
            content = content[offset:]
            await ctx.info(f"Offset applied ({offset} chars)")

        if len(content) > max_chars:
            content = content[:max_chars]
            await ctx.info(f"Report truncated to {max_chars} characters")

        await ctx.info(f"Report read ({len(content)} chars)")
        return content
    except SearchError:
        raise
    except Exception as e:
        await ctx.error(f"Failed to read latest report: {e}")
        raise SearchError(str(e))
