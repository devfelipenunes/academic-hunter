"""MCP tools for paper discovery — citation graph, DOI lookup, topic discovery.

All tools accept a ``ctx`` parameter (auto-injected by FastMCP as ``Context``)
for logging and error reporting.
"""

import requests
from urllib.parse import quote
from academic_hunter import AcademicHunter
from ..cache import cached, discovery_cache
from ._utils import openalex_get, run_blocking
from ..exceptions import DiscoveryError
from ..validation import validate_doi
from mcp.server.fastmcp import Context


#: OpenAlex returns a work's references as bare OpenAlex IDs, which then have to
#: be resolved in a second call. Its `filter` takes at most 100 OR values, and
#: the tool's own contract is a list of ten, so that is the ceiling here.
_REFERENCE_LIMIT = 10


def _rate_limit_error() -> DiscoveryError:
    """The error for a spent OpenAlex budget, in OpenAlex's own terms.

    A 429 here is a cost ceiling, not a burst limit: OpenAlex accepts 100
    requests a second and meters by the credit a call type costs. Saying so
    matters because the remedy is different — a key, or waiting for midnight
    UTC, never "slow down".
    """
    return DiscoveryError(
        "OpenAlex returned 429 — the daily credit budget is spent (about 1000 "
        "credits without a key; a `search` costs 10). Set `api_keys.openalex` "
        "for ten times the budget, or retry after midnight UTC."
    )


@cached(discovery_cache)
async def explore_citation_graph(doi: str, direction: str = "citations", ctx: Context = None) -> str:
    """Explore the citation graph of a paper using its DOI via OpenAlex.

    Both directions are answered from OpenAlex: "citations" filters works by
    `cites:<id>`, and "references" resolves the IDs the work carries. The DOI
    lookup itself is free; each direction costs one credit.

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
        # The singleton is free, and for `references` it is the only way in:
        # a work carries its references as IDs, not as resolvable records.
        work = await openalex_get(
            f"/works/doi:{quote(doi, safe='/')}",
            {"select": "id,display_name,publication_year,cited_by_count,referenced_works"},
        )
        if not work:
            return f"No record for DOI {doi} in OpenAlex."

        if direction == "citations":
            work_id = (work.get("id") or "").rsplit("/", 1)[-1]
            if not work_id:
                return f"No OpenAlex ID for DOI {doi}."
            data = await openalex_get(
                "/works",
                {
                    "filter": f"cites:{work_id}",
                    "per_page": _REFERENCE_LIMIT,
                    "select": "display_name,publication_year,type",
                },
            )
            items = data.get("results") or []
        else:
            referenced = work.get("referenced_works") or []
            if not referenced:
                # OpenAlex has the work but no parsed reference list for it,
                # which is common for conference papers. Saying so is the point:
                # an empty answer here is not "nothing cites this".
                await ctx.info(f"OpenAlex has no indexed references for {doi}")
                return (
                    f"OpenAlex holds no indexed reference list for DOI {doi} "
                    f"(it is cited by {work.get('cited_by_count', 0)} works)."
                )
            ids = "|".join(ref.rsplit("/", 1)[-1] for ref in referenced[:_REFERENCE_LIMIT])
            data = await openalex_get(
                "/works",
                {
                    "filter": f"openalex_id:{ids}",
                    "per_page": _REFERENCE_LIMIT,
                    "select": "display_name,publication_year,type",
                },
            )
            items = data.get("results") or []

        if not items:
            await ctx.info(f"No {direction} found for DOI {doi}")
            return f"No {direction} found for DOI {doi}."

        results = [f"--- {direction.capitalize()} for {doi} ---"]
        for item in items:
            title = item.get("display_name") or "Unknown Title"
            year = item.get("publication_year") or "Unknown Year"
            # OpenAlex indexes a paper's preprint and its published version as
            # two works with the same title, so the same line appeared twice
            # with nothing to tell them apart. Naming the preprint is what makes
            # the pair readable rather than looking like a duplicate bug.
            marker = " [preprint]" if item.get("type") == "preprint" else ""
            results.append(f"- {title} ({year}){marker}")

        await ctx.info(f"Found {len(items)} {direction}")
        return "\n".join(results)
    except DiscoveryError:
        raise
    except ValueError as e:
        raise DiscoveryError(str(e))
    except requests.RequestException as e:
        status = getattr(getattr(e, "response", None), "status_code", 0)
        if status == 429:
            await ctx.error("OpenAlex is over its daily budget for this client.")
            raise _rate_limit_error()
        await ctx.error(f"OpenAlex API error: {e}")
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
    """Performs a quick topic search via OpenAlex.

    Returns the titles of the most relevant papers to help identify jargon
    before configuring the full search.

    A `search` is OpenAlex's most expensive call type — 10 of the roughly 1000
    daily credits a keyless caller gets — so the result is cached.
    """
    await ctx.info(f"Running quick topic discovery for '{topic}'...")

    try:
        # Keyword arguments rather than a pasted query string: a topic is
        # operator input, and building the URL by hand let an `&` in it add a
        # parameter of its own.
        data = await openalex_get(
            "/works",
            {
                "search": topic,
                "per_page": 10,
                "select": "display_name,publication_year",
            },
        )

        items = data.get("results") or []
        if not items:
            await ctx.info(f"No results found for topic: {topic}")
            return f"No results found for topic: {topic}"

        results = [f"--- Quick Discovery for '{topic}' ---"]
        for work in items:
            title = work.get("display_name") or "Unknown Title"
            year = work.get("publication_year") or "Unknown Year"
            results.append(f"- {title} ({year})")

        await ctx.info(f"Found {len(items)} papers for '{topic}'")
        return "\n".join(results)
    except DiscoveryError:
        raise
    except requests.RequestException as e:
        status = getattr(getattr(e, "response", None), "status_code", 0)
        if status == 429:
            await ctx.error("OpenAlex is over its daily budget for this client.")
            raise _rate_limit_error()
        await ctx.error(f"OpenAlex API error: {e}")
        raise DiscoveryError(str(e))
    except Exception as e:
        await ctx.error(f"Unexpected error discovering topic: {e}")
        raise DiscoveryError(str(e))
