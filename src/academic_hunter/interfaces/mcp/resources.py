"""MCP resource functions — expose data as read-only content.

Each function is registered via ``mcp.resource()`` in server.py.
"""

import json as _json
import logging
from urllib.parse import unquote

from .tools._utils import read_store_stats, run_blocking

logger = logging.getLogger("academic_hunter.mcp.resources")

LATEST_REPORT_MAX_CHARS = 10000


def _with_truncation_notice(content: str, limit: int) -> str:
    """The content cut to ``limit``, saying so when it had to be cut.

    A bare slice returns a document that simply stops mid-sentence, which reads
    as the report's own ending: the client summarises a fragment and has no way
    to know. A report is the one artifact where the tail is the conclusion.
    """
    if len(content) <= limit:
        return content
    return (
        content[:limit]
        + f"\n\n---\n\n_[truncated: {len(content) - limit} of {len(content)} "
        "characters omitted. The full file is on disk.]_\n"
    )


async def get_config_resource() -> str:
    """Return the current Academic Hunter configuration as a JSON string.

    URI: ``academic-hunter://config/current``
    """
    from academic_hunter.core import get_config

    config = get_config()
    data = {
        "settings": config.public_settings(),
        "anchors": config.anchors,
        "technical_strings": config.tech_strings,
        "technical_weights": config.tech_weights,
        "context_rules": config.context_rules,
        "keyword_only_terms": config.keyword_only_terms,
        "keyword_only_category": config.keyword_only_category,
        "blocked_sources": list(config.blocked_sources),
    }
    return _json.dumps(data, ensure_ascii=False, indent=2)


async def get_latest_report_resource() -> str:
    """Return the content of the most recently generated report (.md).

    URI: ``academic-hunter://reports/latest``
    """
    from academic_hunter.core.infra import paths

    from .tools._utils import _latest_report_path, get_project_root

    results_dir = get_project_root() / paths.RESULTS_DIRNAME
    if not results_dir.exists():
        return "No report available"

    latest = _latest_report_path(results_dir)
    if latest is None:
        return "No report available"

    content = latest.read_text(encoding="utf-8", errors="replace")
    return _with_truncation_notice(content, LATEST_REPORT_MAX_CHARS)


async def get_vector_stats_resource() -> str:
    """Return vector-store statistics as JSON.

    URI: ``academic-hunter://vector-store/stats``
    """
    try:
        from .tools._utils import _get_vector_store

        store = await run_blocking(_get_vector_store)
        if store is None:
            return _json.dumps(
                {"available": False, "error": "Vector store not available"},
                ensure_ascii=False,
                indent=2,
            )
        collections, collection_data, total_papers = await run_blocking(read_store_stats, store)

        return _json.dumps(
            {
                "available": True,
                "collection_count": len(collections),
                "total_papers": total_papers,
                "collections": collection_data,
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as exc:
        logger.warning("Resource error: %s", exc)
        return _json.dumps(
            {"available": False, "error": str(exc)},
            ensure_ascii=False,
            indent=2,
        )


async def get_paper_resource(doi: str) -> str:
    """Return metadata (including abstract) for a paper by DOI.

    URI: ``academic-hunter://papers/{doi}``, with the DOI **percent-encoded** —
    ``academic-hunter://papers/10.48550%2FarXiv.2101.00001``. A DOI carries a
    slash between its prefix and its suffix, and the URI template matches a
    single path segment, so a DOI written literally reaches no handler at all
    ("Unknown resource"). The encoded form matches, and it is decoded here
    because it arrives still encoded.
    """
    doi = unquote(doi)
    try:
        from academic_hunter import AcademicHunter

        hunter = await run_blocking(AcademicHunter)
        abstract = await run_blocking(hunter.fetch_abstract_by_doi, doi)
        if abstract:
            return _json.dumps(
                {"doi": doi, "found": True, "abstract": abstract},
                ensure_ascii=False,
                indent=2,
            )
        return _json.dumps(
            {"doi": doi, "found": False, "error": "No abstract found"},
            ensure_ascii=False,
            indent=2,
        )
    except Exception as exc:
        return _json.dumps(
            {"doi": doi, "found": False, "error": str(exc)},
            ensure_ascii=False,
            indent=2,
        )
