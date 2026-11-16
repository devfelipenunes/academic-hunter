"""MCP tools for paper discovery — citation graph, DOI lookup, topic discovery.

All tools accept a ``ctx`` parameter (auto-injected by FastMCP as ``Context``)
for logging and error reporting.
"""

import json
import re
from collections import Counter
from urllib.parse import quote

import requests

from academic_hunter import AcademicHunter
from mcp.server.fastmcp import Context

from ..cache import cached, discovery_cache, discovery_titles
from ..exceptions import DiscoveryError
from ..validation import validate_doi
from ._utils import _STOPWORDS, _is_generic, openalex_get, run_blocking
from .trending import _extract_bigrams

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

    Bypasses the pipeline: one source directly, so no run and no report. For a
    literature review run `quick_topic_discovery`, then `update_config`, then
    `run_search`; use this for the specific lookup the user asked for.

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

    Bypasses the pipeline: one source directly, so no run and no report. For a
    literature review run `quick_topic_discovery`, then `update_config`, then
    `run_search`; use this for the specific lookup the user asked for.

    Useful when you need specific details about a single paper without
    running a full search.
    """
    await ctx.info(f"Fetching paper by DOI {doi}...")
    try:
        hunter = await run_blocking(AcademicHunter)
        abstract = await run_blocking(hunter.fetch_abstract_by_doi, doi)
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

    Bypasses the pipeline: one source directly, so no run and no report. For a
    literature review run `quick_topic_discovery`, then `update_config`, then
    `run_search`; use this for the specific lookup the user asked for.

    Useful for reading multiple papers at once to generate a literature
    review matrix or summary.
    """
    await ctx.info(f"Fetching abstracts for {len(dois)} DOIs...")
    try:
        hunter = await run_blocking(AcademicHunter)

        def _fetch_all() -> list:
            results = []
            for doi in dois:
                abstract = hunter.fetch_abstract_by_doi(doi)
                if abstract:
                    results.append(f"--- Abstract for {doi} ---\n{abstract}\n")
                else:
                    results.append(f"--- Abstract for {doi} ---\n[Not found]\n")
            return results

        results = await run_blocking(_fetch_all)
        await ctx.info(f"Retrieved {len(results)} abstracts")
        return "\n".join(results)
    except DiscoveryError:
        raise
    except Exception as e:
        await ctx.error(f"Failed to fetch multiple abstracts: {e}")
        raise DiscoveryError(str(e))


_DISCOVERY_PER_PAGE = 100
_DISCOVERY_PRINTED_TITLES = 10
_CANDIDATE_TERM_LIMIT = 30


def _candidate_terms(titles: list) -> dict:
    """The terms the retrieved titles use, counted, with no structure imposed.

    This used to hand back a finished shape -- one anchor group, one technical
    category, every weight flat at 1.5 -- built from whatever the ten retrieved
    titles repeated most. Ten titles are not a field: for an ambiguous topic the
    sample is mostly off-topic, and a frequency count over it lifts the words
    every field uses to the same height as the field's own. The draft then
    arrived with its shape already decided, and a shape is what an agent keeps;
    "review the draft" does not undo anchors it was handed.

    So the counts come back as evidence and the structure stays with the caller,
    who is the one that knows the field. ``generic`` marks a term rather than
    removing it: such a term is still a legitimate thing to score a paper on,
    and only the caller knows whether this is a topic where it means something.
    """
    counts: Counter = Counter()
    for title in titles:
        for bigram in _extract_bigrams(title, _STOPWORDS):
            counts[bigram] += 1
        for word in re.findall(r"[a-zA-Z][a-zA-Z\-]{1,}", title.lower()):
            if word not in _STOPWORDS and len(word) > 2:
                counts[word] += 1

    terms = []
    for term, seen in counts.most_common(_CANDIDATE_TERM_LIMIT):
        entry = {"term": term, "titles": seen}
        if _is_generic(term):
            entry["generic"] = True
        terms.append(entry)
    return {"titles_counted": len(titles), "candidate_terms": terms}


@cached(discovery_cache)
async def quick_topic_discovery(topic: str, ctx: Context) -> str:
    """Performs a quick topic search via OpenAlex.

    Returns the titles of the most relevant papers and the terms those titles
    use, counted, so `technical_strings` can be written from the field's own
    vocabulary rather than from the model's memory of it — an empty or guessed
    mapping is what leaves four of the six sources unqueried.

    It returns no anchors, no categories and no weights. Ten titles were never
    enough to infer a field's shape, and a shape handed over is a shape kept, so
    the counts come back as evidence and the configuration is written by the
    caller, who knows the field. `update_config` then reports what the
    configuration it accepted will fail to do.

    The hundred titles are kept for the life of the session, so that report can
    hold the anchors against them: an anchor appearing in none of the titles
    this topic actually retrieved is one written from memory rather than from
    the literature, and when most of a group does, the topic word belongs to
    another field.

    A `search` is OpenAlex's most expensive call type — 10 of the roughly 1000
    daily credits a keyless caller gets — and that cost does not grow with
    `per_page`, so a hundred titles are counted while ten are shown. The result
    is cached.
    """
    await ctx.info(f"Running quick topic discovery for '{topic}'...")

    try:
        data = await openalex_get(
            "/works",
            {
                "search": topic,
                "per_page": _DISCOVERY_PER_PAGE,
                "select": "display_name,publication_year",
            },
        )

        items = data.get("results") or []
        if not items:
            await ctx.info(f"No results found for topic: {topic}")
            return f"No results found for topic: {topic}"

        results = [f"--- Quick Discovery for '{topic}' ---"]
        for work in items[:_DISCOVERY_PRINTED_TITLES]:
            title = work.get("display_name") or "Unknown Title"
            year = work.get("publication_year") or "Unknown Year"
            results.append(f"- {title} ({year})")
        if len(items) > _DISCOVERY_PRINTED_TITLES:
            results.append(
                f"  (and {len(items) - _DISCOVERY_PRINTED_TITLES} more, not shown)"
            )

        titles = [work.get("display_name") or "" for work in items]
        candidates = _candidate_terms(titles)
        discovery_titles.set(
            topic, {"topic": topic, "titles": titles, "candidates": candidates}
        )
        results.append("")
        results.append(
            f"The terms these titles use, counted over all "
            f"{candidates['titles_counted']} of them. This is evidence, not a "
            "configuration: it carries no anchors, no categories and no weights, "
            "because those are the field's shape and the shape is yours to "
            "decide. A term marked \"generic\" names any field's work — as a "
            "scoring term it is fine, but as an anchor it admits every paper "
            "that uses the word, since the anchor gate accepts any one term of "
            "the first group that matches. Pick anchors specific to this topic, "
            "then give update_config the categories — at least four — and the "
            "weights you know the field uses. It reports back what the "
            "configuration it accepts will fail to do."
        )
        results.append("")
        results.append(
            "One trap worth naming, because it is the likeliest way to get an "
            "empty run: an anchor matches as a whole phrase, so the topic "
            "written verbatim usually matches no title at all. Measured on a "
            "real run, a topic used as its own only anchor dropped all 11 "
            "papers at the gate before anything scored them. Anchor on the "
            "phrases the titles above actually use."
        )
        results.append("")
        results.append(json.dumps(candidates, indent=2, ensure_ascii=False))

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
