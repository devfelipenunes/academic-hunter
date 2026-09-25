"""MCP tools for executing the academic search pipeline and reading results.

``run_search`` reports progress through the FastMCP Context when available.
"""

from academic_hunter import AcademicHunter
from academic_hunter.core.infra import paths
from ._utils import _latest_report_path, get_project_root, run_blocking
from ..exceptions import SearchError
from mcp.server.fastmcp import Context


def _coverage(hunter) -> str:
    """Which sources were actually queried this run, and what each returned.

    A source the pipeline skipped and a source that was queried and found
    nothing both read as 0 everywhere else. They are not the same thing, and
    without this the agent has no way to tell them apart.
    """
    queried = {item.get("Source") for item in hunter.query_history}
    identified = hunter.stats.get("identified", {})
    grid = [
        name for name, connector in hunter.connectors.items() if not getattr(connector, "is_keyword_only", False)
    ]

    lines = ["", "Coverage by source:"]
    skipped = []
    for name, count in identified.items():
        if name in queried:
            lines.append(f"  {name}: {count}")
        else:
            lines.append(f"  {name}: NOT QUERIED")
            skipped.append(name)
    lines.append(f"Identified: {sum(identified.values())} | Included: {hunter.stats.get('included_final', 0)}")

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
        # The pipeline joins connector threads and paces requests: minutes of
        # wall clock that would otherwise freeze every other tool on the server.
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
            return "Error: No results directory found. Have you run a search yet?"

        latest_file = _latest_report_path(results_dir)
        if latest_file is None:
            await ctx.info("No markdown reports found in results/")
            return "Error: No markdown reports found in results/."
        with open(latest_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Apply offset
        if offset > 0:
            content = content[offset:]
            await ctx.info(f"Offset applied ({offset} chars)")

        # Truncate to max_chars
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
