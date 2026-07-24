"""MCP tools for paper discovery — citation graph, DOI lookup, topic discovery.

All tools accept a ``ctx`` parameter (auto-injected by FastMCP as ``Context``)
for logging and error reporting.
"""

import requests
from academic_hunter import AcademicHunter
from ..exceptions import DiscoveryError


def explore_citation_graph(doi: str, direction: str = "citations", ctx=None) -> str:
    """Explore the citation graph of a paper using its DOI via Semantic Scholar.

    Args:
        doi: The DOI of the paper to explore.
        ctx: FastMCP Context (auto-injected).
        direction: "citations" (papers that cited this DOI) or "references".
    """
    ctx.info(f"Exploring {direction} for DOI {doi}...")
    if direction not in ("citations", "references"):
        raise DiscoveryError("direction must be 'citations' or 'references'.")

    try:
        paper_id = f"DOI:{doi}"
        url = (
            f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}"
            f"/{direction}?fields=title,year,authors&limit=10"
        )
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json().get("data", [])
        if not data:
            ctx.info(f"No {direction} found for DOI {doi}")
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

        ctx.info(f"Found {len(data)} {direction}")
        return "\n".join(results)
    except DiscoveryError:
        raise
    except requests.RequestException as e:
        ctx.error(f"Semantic Scholar API error: {e}")
        raise DiscoveryError(str(e))
    except Exception as e:
        ctx.error(f"Unexpected error exploring citation graph: {e}")
        raise DiscoveryError(str(e))


def fetch_paper_by_doi(doi: str, ctx) -> str:
    """Fetches the abstract and metadata for a specific paper using its DOI.

    Useful when you need specific details about a single paper without
    running a full search.
    """
    ctx.info(f"Fetching paper by DOI {doi}...")
    try:
        hunter = AcademicHunter()
        abstract = hunter.fetch_abstract_by_doi(doi)
        if abstract:
            ctx.info(f"Abstract found for DOI {doi}")
            return f"Abstract found for DOI {doi}:\n{abstract}"
        ctx.info(f"No abstract found for DOI {doi}")
        return f"No abstract could be retrieved for DOI {doi}."
    except DiscoveryError:
        raise
    except Exception as e:
        ctx.error(f"Failed to fetch paper {doi}: {e}")
        raise DiscoveryError(str(e))


def fetch_multiple_abstracts(dois: list[str], ctx) -> str:
    """Fetches the abstracts for a list of DOIs.

    Useful for reading multiple papers at once to generate a literature
    review matrix or summary.
    """
    ctx.info(f"Fetching abstracts for {len(dois)} DOIs...")
    try:
        hunter = AcademicHunter()
        results = []
        for doi in dois:
            abstract = hunter.fetch_abstract_by_doi(doi)
            if abstract:
                results.append(f"--- Abstract for {doi} ---\n{abstract}\n")
            else:
                results.append(f"--- Abstract for {doi} ---\n[Not found]\n")
        ctx.info(f"Retrieved {len(results)} abstracts")
        return "\n".join(results)
    except DiscoveryError:
        raise
    except Exception as e:
        ctx.error(f"Failed to fetch multiple abstracts: {e}")
        raise DiscoveryError(str(e))


def quick_topic_discovery(topic: str, ctx) -> str:
    """Performs a quick topic search via the Semantic Scholar API.

    Returns the titles of the most relevant papers to help identify jargon
    before configuring the full search.
    """
    ctx.info(f"Running quick topic discovery for '{topic}'...")
    try:
        url = (
            f"https://api.semanticscholar.org/graph/v1/paper/search"
            f"?query={topic}&limit=10&fields=title,year"
        )
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json().get("data", [])
        if not data:
            ctx.info(f"No results found for topic: {topic}")
            return f"No results found for topic: {topic}"

        results = [f"--- Quick Discovery for '{topic}' ---"]
        for paper in data:
            title = paper.get("title", "Unknown Title")
            year = paper.get("year", "Unknown Year")
            results.append(f"- {title} ({year})")

        ctx.info(f"Found {len(data)} papers for '{topic}'")
        return "\n".join(results)
    except DiscoveryError:
        raise
    except requests.RequestException as e:
        ctx.error(f"Semantic Scholar API error: {e}")
        raise DiscoveryError(str(e))
    except Exception as e:
        ctx.error(f"Unexpected error discovering topic: {e}")
        raise DiscoveryError(str(e))
