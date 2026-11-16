"""One tool for the sources a review queries one at a time.

Five tools used to sit here — ``search_openaire``, ``search_europepmc``,
``search_biorxiv``, ``search_datasets`` and ``search_patents`` — and the agent
saw five peers of ``run_search``. Measured on a fresh install, it picked one of
them instead of the pipeline. They are one operation with a parameter, so they
are one tool with a parameter: `search_source` queries exactly one external
service and, like every other on-demand tool, produces no run and no report.

The bodies did not merge because they are not the same. What merged is what was
copied: six identical request-and-decode blocks across the tool set, and the
same three-line Markdown head in each of these five. What stays is what differs
— OpenAIRE's XML-shaped JSON, the bearer token Lens will not serve without,
DataCite's resource types.

Two of the five are gone, and one was never a single source. Europe PMC,
bioRxiv and medRxiv index medicine and the life sciences, and no review this
project is used for is in those fields: three entries that returned nothing,
on a surface that said otherwise. What is left is a general index of funded
research, a data repository, and a patent register.

The full-text step still reads from Europe PMC, and that is deliberate — it is
a way of getting the text of a paper rather than a collection to search, and it
is the only one that needs neither the `fulltext` extra nor an open-access PDF.
"""

import asyncio
from typing import Any, Dict, List, Tuple

import requests

from mcp.server.fastmcp import Context

from ..exceptions import DiscoveryError

DEFAULT_LIMIT = 10
DEFAULT_TIMEOUT = 15

SOURCES: Dict[str, Dict[str, Any]] = {
    "openaire": {"label": "OpenAIRE", "heading": "OpenAIRE Results", "ceiling": 50},
    "datacite": {"label": "DataCite", "heading": "DataCite Results", "ceiling": 50},
    "lens": {"label": "Lens.org", "heading": "Patent Search", "ceiling": 25},
}

SOURCE_NAMES = tuple(SOURCES)

UNSUPPORTED = (
    "Unsupported source. Use one of: " + ", ".join(SOURCE_NAMES) + "."
)


def _head(heading: str, query: str, total_label: str, total: Any) -> List[str]:
    """The three lines every one of these replies opens with."""
    return [f"# {heading}: {query}\n", f"**{total_label}:** {total}\n", "---\n"]


def _reported_total(candidate: Any, fallback: int) -> int:
    """Use the API's match count when present, otherwise report fetched rows."""
    try:
        return max(0, int(candidate)) if candidate is not None else fallback
    except (TypeError, ValueError):
        return fallback


async def _get_json(url: str, params: Dict[str, Any]) -> Any:
    """One GET, decoded. Deliberately not wrapped: every caller already is.

    The tools that use it catch broadly and re-raise as ``DiscoveryError``,
    around the parsing as well as the request, and moving that boundary here
    would change which failures come back as a tool error and which escape.
    """
    response = await asyncio.to_thread(requests.get, url, params=params, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    return response.json()


async def _search_openaire(query: str, limit: int) -> Tuple[Any, List[str]]:
    params = {"keywords": query, "size": limit, "format": "json"}
    data = await _get_json("https://api.openaire.eu/search/publications", params)

    container = data.get("response", {}).get("results", {}) or {}
    results = container.get("result", []) if isinstance(container, dict) else container or []

    blocks = []
    for i, result in enumerate(results[:limit], 1):
        oaf = result.get("metadata", {}).get("oaf:entity", {}).get("oaf:result", {})
        meta = _openaire_meta(oaf)
        blocks.append([
            f"## {i}. {meta['title'] or 'Untitled'} {meta['oa']}\n",
            f"- **Authors:** {meta['authors']}\n",
            f"- **Date:** {meta['date']}\n",
            *([f"- **Funder:** {meta['funder']}\n"] if meta["funder"] else []),
            *([f"- **DOI:** `{meta['doi']}`\n"] if meta["doi"] else []),
            "",
        ])
    header = data.get("response", {}).get("header", {})
    total = _reported_total(header.get("numFound", header.get("total")), len(results))
    return total, blocks


def _openaire_list(node) -> list:
    """OAI-PMH's XML→JSON conversion gives a dict for one value, a list for many.

    Every field in this format has the same shape, and the guard existed on
    `project` alone — the others iterated the dict's *keys* and called `.get` on
    the resulting strings.
    """
    if node is None:
        return []
    return node if isinstance(node, list) else [node]


def _openaire_meta(oaf: Dict[str, Any]) -> Dict[str, Any]:
    """Extract flat metadata from OpenAIRE's nested oaf:result structure."""
    title_list = _openaire_list(oaf.get("title"))
    title = ""
    for candidate in title_list:
        if candidate.get("@classid") == "main title":
            title = candidate.get("$", "")
            break
    if not title and title_list:
        title = title_list[0].get("$", "")

    creators = _openaire_list(oaf.get("creator"))
    authors = "; ".join(c.get("$", "") for c in creators[:5] if isinstance(c, dict)) or "?"

    date_acc = oaf.get("dateofacceptance", {})
    pub_date = date_acc.get("$", "?")[:10] if isinstance(date_acc, dict) else "?"

    pids = _openaire_list(oaf.get("pid"))
    doi = ""
    for pid in pids:
        if isinstance(pid, dict) and pid.get("@classid") == "doi":
            doi = pid.get("$", "")
            break

    access = _openaire_list(oaf.get("bestaccessright"))
    is_oa = "" if not access or not isinstance(access[0], dict) else (
        "✅ OA" if access[0].get("@classid") == "OPEN ACCESS" else ""
    )

    projects = oaf.get("project", [])
    funder = ""
    if isinstance(projects, dict):
        projects = [projects]
    for project in projects[:3]:
        funder_node = project.get("funder", {})
        if isinstance(funder_node, dict):
            name = funder_node.get("$", "") or funder_node.get("@classname", "")
            if name:
                funder = name

    return {
        "title": title, "authors": authors, "date": pub_date,
        "doi": doi, "oa": is_oa, "funder": funder,
    }


async def _search_datacite(query: str, limit: int, resource_type: str) -> Tuple[Any, List[str]]:
    params: Dict[str, Any] = {
        "query": query,
        "page[size]": limit,
        "sort": "publicationYear desc,updated desc",
    }
    if resource_type:
        params["resource-type-id"] = resource_type

    data = await _get_json("https://api.datacite.org/dois", params)
    results = data.get("data", [])

    blocks = []
    for i, item in enumerate(results[:limit], 1):
        attrs = item.get("attributes", {})
        creators = attrs.get("creators", [])
        related = attrs.get("relatedIdentifiers", [])
        doi = attrs.get("doi", "")
        publisher = attrs.get("publisher", "")

        blocks.append([
            f"## {i}. {(attrs.get('titles') or [{}])[0].get('title', 'Untitled')}\n",
            f"- **Type:** {attrs.get('resourceTypeGeneral', '')} | **Year:** {attrs.get('publicationYear', '?')}\n",
            f"- **Authors:** {'; '.join(c.get('name', '') for c in creators[:4]) or '?'}\n",
            *([f"- **DOI:** `{doi}`\n"] if doi else []),
            *([f"- **Publisher:** {publisher}\n"] if publisher else []),
            *([f"- (related to {len(related)} DOIs)\n"] if related else []),
            "",
        ])
    total = _reported_total((data.get("meta") or {}).get("total"), len(results))
    return total, blocks


async def _search_lens(query: str, limit: int) -> Tuple[Any, List[str]]:
    token = _lens_token()
    if not token:
        raise DiscoveryError(
            "Lens.org requires a token. Set LENS_API_KEY in the environment or "
            "settings.api_keys.lens in config.json."
        )

    payload = {"query": {"terms": [{"field": "title", "value": query}]}, "size": limit}
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}

    response = await asyncio.to_thread(
        requests.post, "https://api.lens.org/patent/search",
        json=payload, headers=headers, timeout=DEFAULT_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    patents = data.get("data", [])

    blocks = []
    for i, patent in enumerate(patents[:limit], 1):
        inventors = patent.get("inventor", [])
        ipc = patent.get("classificationIPC", [])
        blocks.append([
            f"## {i}. {patent.get('title', 'Untitled')}\n",
            f"- **Inventors:** {', '.join(inventors[:3]) if inventors else '?'}"
            f" | **Year:** {patent.get('publicationYear', '?')}\n",
            *([f"- **IPC:** {', '.join(ipc[:3])}\n"] if ipc else []),
            "",
        ])
    total = _reported_total(data.get("total"), len(patents))
    return total, blocks


def _lens_token() -> str:
    """The Lens token: environment first, then the config.

    The same order the connectors use, so a key set either way is found.
    """
    import os

    from academic_hunter.core import get_config

    token = os.environ.get("LENS_API_KEY")
    if token:
        return token

    try:
        settings = get_config().settings or {}
    except Exception:
        return ""

    keys = settings.get("api_keys") or {}
    return str(keys.get("lens") or settings.get("lens_api_key") or "")


def _empty_reply(source: str, query: str) -> str:
    """Nothing found, said the way each source used to say it."""
    if source == "lens":
        return f"No patents found for: '{query}'."
    return f"No results found for: '{query}'."


async def search_source(
    ctx: Context,
    source: str,
    query: str,
    limit: int = DEFAULT_LIMIT,
    resource_type: str = "",
) -> str:
    """Searches one external source directly, outside the review pipeline.

    Bypasses the pipeline: one source directly, so no run and no report. For a
    literature review run `quick_topic_discovery`, then `update_config`, then
    `run_search`; use this for the specific lookup the user asked for.

    Each source covers something the six review sources do not:

    - ``openaire`` — publications linked to research grants and funding
    - ``datacite`` — datasets and software, from Zenodo, Figshare and 1000+ more
    - ``lens`` — patents, and requires a token: set ``LENS_API_KEY`` in the
      environment or ``settings.api_keys.lens`` in config.json, or the call
      cannot succeed and says so rather than returning nothing

    Args:
        ctx: FastMCP Context (auto-injected).
        source: Which source to query — see the list above.
        query: Search query, sent to the source's own search.
        limit: Max results (default 10). Capped per source, at 25 for ``lens``
            and 50 for ``openaire`` and ``datacite``.
        resource_type: Only ``datacite`` uses it — ``"dataset"``,
            ``"software"``, ``"text"``. Empty means every type.
    """
    source = source.strip().lower()
    if source not in SOURCES:
        await ctx.error(f"Unsupported source: {source}")
        return UNSUPPORTED

    spec = SOURCES[source]
    label, heading = spec["label"], spec["heading"]
    capped = max(1, min(limit, spec["ceiling"]))

    await ctx.info(f"Searching {label} for: '{query}'...")

    try:
        if source == "openaire":
            total, blocks = await _search_openaire(query, capped)
        elif source == "datacite":
            total, blocks = await _search_datacite(query, capped, resource_type)
        else:
            total, blocks = await _search_lens(query, capped)
    except DiscoveryError as exc:
        await ctx.error(f"{label} search failed: {exc}")
        raise
    except requests.RequestException as exc:
        await ctx.warning(f"{label} API error: {exc}")
        return f"{label} API error: {exc}."
    except Exception as exc:
        await ctx.error(f"{label} search failed: {exc}")
        raise DiscoveryError(str(exc))

    if not blocks:
        await ctx.info(f"No {label} results for '{query}'")
        return _empty_reply(source, query)

    lines = _head(heading, query, "Total", total)
    for block in blocks:
        lines.extend(block)
    await ctx.info(f"Found {total} results from {label}")
    return "\n".join(lines)
