"""MCP tools for executing the academic search pipeline and reading results.

``run_search`` reports progress through the FastMCP Context when available.
"""

from pathlib import Path
from academic_hunter import AcademicHunter
from ._utils import _latest_report_path, get_project_root, run_blocking
from ..exceptions import SearchError
from mcp.server.fastmcp import Context


async def run_search(ctx: Context, limit_per_source: int = None) -> str:
    """Executes the consolidated academic search based on the keywords and weights from config.json.

    Use this tool only after having configured config.json with update_config (if necessary).

    Args:
        ctx: FastMCP Context (auto-injected).
        limit_per_source: Max results per API source (default: from config).
    """
    await ctx.info("Starting academic search pipeline...")
    await ctx.report_progress(0, 3, "Initializing hunter")
    try:
        project_root = get_project_root()
        output_dir = str(project_root / "results")
        hunter = await run_blocking(AcademicHunter, output_dir=output_dir)

        if limit_per_source is None:
            limit_per_source = hunter.config.settings.get("limit_per_query", 100)

        await ctx.report_progress(1, 3, f"Querying academic APIs (limit={limit_per_source})")
        # The pipeline joins connector threads and paces requests: minutes of
        # wall clock that would otherwise freeze every other tool on the server.
        report_path = await run_blocking(hunter.run, limit_per_source=limit_per_source)

        await ctx.report_progress(2, 3, "Finalizing report")
        await ctx.info(f"Search completed. Report at: {report_path}")
        await ctx.report_progress(3, 3, "Complete")

        return f"Search completed successfully. Report generated at: {report_path}"
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
        project_root = get_project_root()
        results_dir = project_root / "results"
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
