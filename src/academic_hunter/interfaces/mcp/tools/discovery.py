"""MCP tools for paper discovery — citation graph, DOI lookup, topic discovery.

All tools accept a ``ctx`` parameter (auto-injected by FastMCP as ``Context``)
for logging and error reporting.
"""

import asyncio
import requests
from academic_hunter import AcademicHunter
from ..cache import cached, discovery_cache
from ._utils import run_blocking
from ..exceptions import DiscoveryError
from ..validation import validate_doi, validate_topic
from mcp.server.fastmcp import Context


async def _request_with_retry(url, max_retries=3, base_delay=2.0, **kwargs):
    """GET request with exponential backoff on 429 rate-limit responses.

    Uses ``asyncio.sleep()`` and ``run_in_executor`` to avoid blocking
    the async event loop during retry delays.
    """
    loop = asyncio.get_event_loop()
    for attempt in range(max_retries):
        response = await loop.run_in_executor(
            None, lambda: requests.get(url, timeout=10, **kwargs)
        )
        if response.status_code == 429:
            delay = base_delay * (2 ** attempt)
            await asyncio.sleep(delay)
            continue
        response.raise_for_status()
        return response
    # Last attempt — let exception propagate
    response = await loop.run_in_executor(
        None, lambda: requests.get(url, timeout=10, **kwargs)
    )
    response.raise_for_status()
    return response


@cached(discovery_cache)
async def explore_citation_graph(doi: str, direction: str = "citations", ctx: Context = None) -> str:
    """Explore the citation graph of a paper using its DOI via Semantic Scholar.

    Args:
        doi: The DOI of the paper to explore.
        ctx: FastMCP Context (auto-injected).
        direction: "citations" (papers that cited this DOI) or "references".
    """
    await ctx.info(f"Exploring {direction} for DOI {doi}...")
    if direction not in ("citations", "references"):
        raise DiscoveryError("direction must be 'citations' or 'references'.")

    try:
        doi = validate_doi(doi)
        paper_id = f"DOI:{doi}"
        url = (
            f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}"
            f"/{direction}?fields=title,year,authors&limit=10"
        )
        response = await _request_with_retry(url)
        response.raise_for_status()

        data = response.json().get("data", [])
        if not data:
            await ctx.info(f"No {direction} found for DOI {doi}")
            return f"No {direction} found for DOI {doi}."

        key = "citingPaper" if direction == "citations" else "citedPaper"
        results = [f"--- {direction.capitalize()} for {doi} ---"]
        for item in data:
            paper = item.get(key)
            if not paper:
                continue
            title = paper.get("title", "Unknown Title")
            year = paper.get("year", "Unknown Year")
            results.append(f"- {title} ({year})")

        await ctx.info(f"Found {len(data)} {direction}")
        return "\n".join(results)
    except DiscoveryError:
        raise
    except ValueError as e:
        raise DiscoveryError(str(e))
    except requests.RequestException as e:
        await ctx.error(f"Semantic Scholar API error: {e}")
        raise DiscoveryError(str(e))
    except Exception as e:
        await ctx.error(f"Unexpected error exploring citation graph: {e}")
        raise DiscoveryError(str(e))


async def fetch_paper_by_doi(doi: str, ctx: Context) -> str:
    """Fetches the abstract and metadata for a specific paper using its DOI.

    Useful when you need specific details about a single paper without
    running a full search.
    """
    await ctx.info(f"Fetching paper by DOI {doi}...")
    try:
        hunter = await run_blocking(AcademicHunter)
        abstract = hunter.fetch_abstract_by_doi(doi)
        if abstract:
            await ctx.info(f"Abstract found for DOI {doi}")
            return f"Abstract found for DOI {doi}:\n{abstract}"
        await ctx.info(f"No abstract found for DOI {doi}")
        return f"No abstract could be retrieved for DOI {doi}."
    except DiscoveryError:
        raise
    except Exception as e:
        await ctx.error(f"Failed to fetch paper {doi}: {e}")
        raise DiscoveryError(str(e))


async def fetch_multiple_abstracts(dois: list[str], ctx: Context) -> str:
    """Fetches the abstracts for a list of DOIs.

    Useful for reading multiple papers at once to generate a literature
    review matrix or summary.
    """
    await ctx.info(f"Fetching abstracts for {len(dois)} DOIs...")
    try:
        hunter = await run_blocking(AcademicHunter)
        results = []
        for doi in dois:
            abstract = hunter.fetch_abstract_by_doi(doi)
            if abstract:
                results.append(f"--- Abstract for {doi} ---\n{abstract}\n")
            else:
                results.append(f"--- Abstract for {doi} ---\n[Not found]\n")
        await ctx.info(f"Retrieved {len(results)} abstracts")
        return "\n".join(results)
    except DiscoveryError:
        raise
    except Exception as e:
        await ctx.error(f"Failed to fetch multiple abstracts: {e}")
        raise DiscoveryError(str(e))


@cached(discovery_cache)
async def quick_topic_discovery(topic: str, ctx: Context) -> str:
    """Performs a quick topic search via the Semantic Scholar API.

    Returns the titles of the most relevant papers to help identify jargon
    before configuring the full search.
    """
    await ctx.info(f"Running quick topic discovery for '{topic}'...")
    try:
        url = (
            f"https://api.semanticscholar.org/graph/v1/paper/search"
            f"?query={topic}&limit=10&fields=title,year"
        )
        response = await _request_with_retry(url)
        response.raise_for_status()

        data = response.json().get("data", [])
        if not data:
            await ctx.info(f"No results found for topic: {topic}")
            return f"No results found for topic: {topic}"

        results = [f"--- Quick Discovery for '{topic}' ---"]
        for paper in data:
            title = paper.get("title", "Unknown Title")
            year = paper.get("year", "Unknown Year")
            results.append(f"- {title} ({year})")

        await ctx.info(f"Found {len(data)} papers for '{topic}'")
        return "\n".join(results)
    except DiscoveryError:
        raise
    except requests.RequestException as e:
        await ctx.error(f"Semantic Scholar API error: {e}")
        raise DiscoveryError(str(e))
    except Exception as e:
        await ctx.error(f"Unexpected error discovering topic: {e}")
        raise DiscoveryError(str(e))
