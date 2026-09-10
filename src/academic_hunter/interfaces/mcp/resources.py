import logging

logger = logging.getLogger("academic_hunter.mcp.resources")
"""MCP resource functions — expose data as read-only content.

Each function is registered via ``mcp.resource()`` in server.py.
"""

import json as _json


async def get_config_resource() -> str:
    """Return the current Academic Hunter configuration as a JSON string.

    URI: ``academic-hunter://config/current``
    """
    from academic_hunter.core import get_config

    config = get_config()
    data = {
        # Redacted: resources are read by the MCP client, same as `read_config`.
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
    from .tools._utils import get_project_root

    results_dir = get_project_root() / "results"
    if not results_dir.exists():
        return "No report available"

    md_files = sorted(
        results_dir.glob("**/*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not md_files:
        return "No report available"

    content = md_files[0].read_text(encoding="utf-8", errors="replace")
    return content[:10000]


async def get_vector_stats_resource() -> str:
    """Return vector-store statistics as JSON.

    URI: ``academic-hunter://vector-store/stats``
    """
    try:
        from .tools._utils import _get_vector_store

        store = _get_vector_store()
        if store is None:
            return _json.dumps(
                {"available": False, "error": "Vector store not available"},
                ensure_ascii=False,
                indent=2,
            )
        collections = store.list_collections()
        total_papers = 0
        collection_data = []
        for coll_name in collections:
            stats = store.collection_stats(coll_name)
            total_papers += stats.get("count", 0)
            collection_data.append(stats)

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

    URI: ``academic-hunter://papers/{doi}``
    """
    try:
        from academic_hunter import AcademicHunter

        hunter = AcademicHunter()
        abstract = hunter.fetch_abstract_by_doi(doi)
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
