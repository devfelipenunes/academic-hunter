"""Shared fixtures for MCP tool tests.

All MCP test files import from here to ensure consistent mock patterns.
Uses pytest fixtures and unittest.mock throughout.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest


@pytest.fixture
def mock_ctx():
    """Standard mock for FastMCP Context.

    Auto-injected by FastMCP when a tool parameter is type-hinted as ``Context``.
    In unit tests we inject this mock directly.
    """
    ctx = AsyncMock()
    ctx.info = MagicMock()
    ctx.error = MagicMock()
    ctx.warning = MagicMock()
    ctx.debug = MagicMock()
    ctx.report_progress = AsyncMock()
    return ctx


@pytest.fixture
def mock_hunter():
    """Mock ``AcademicHunter`` so no real config, cache, or APIs are touched."""
    with patch("academic_hunter.interfaces.mcp.tools.search.AcademicHunter") as m:
        instance = m.return_value
        # Default: ``run()`` returns a dummy report path
        instance.run.return_value = "/tmp/dummy/report.md"
        yield instance


@pytest.fixture
def mock_hunter_rag():
    """Mock ``AcademicHunter`` specifically for RAG tool tests."""
    with patch("academic_hunter.interfaces.mcp.tools.rag.AcademicHunter") as m:
        yield m.return_value


@pytest.fixture
def mock_vector_store():
    """Mock ``ChromaVectorStore`` so no real ChromaDB is needed."""
    with patch(
        "academic_hunter.interfaces.mcp.tools.rag.ChromaVectorStore"
    ) as m:
        instance = m.return_value
        # Default: empty query result
        instance.query.return_value = []
        instance.collection_stats.return_value = {"count": 0}
        instance.list_collections.return_value = []
        instance.index_papers.return_value = True
        yield instance


@pytest.fixture
def mock_hunter_config():
    """Mock ``HunterConfig`` for configuration tool tests."""
    with patch(
        "academic_hunter.interfaces.mcp.tools.configuration.HunterConfig"
    ) as m:
        instance = m.return_value
        instance.settings = {"start_year": 2020, "limit_per_query": 100}
        instance.anchors = {}
        instance.tech_strings = {}
        instance.tech_weights = {}
        instance.context_rules = {}
        instance.keyword_only_terms = []
        instance.keyword_only_category = ""
        instance.save = MagicMock()
        yield instance


@pytest.fixture
def mock_discovery_hunter():
    """Mock ``AcademicHunter`` for discovery tool tests."""
    with patch(
        "academic_hunter.interfaces.mcp.tools.discovery.AcademicHunter"
    ) as m:
        instance = m.return_value
        instance.fetch_abstract_by_doi.return_value = (
            "Abstract of a groundbreaking paper."
        )
        yield instance


@pytest.fixture
def mock_obsidian_config():
    """Mock ``HunterConfig`` with an ``obsidian_vault_path`` set."""
    with patch(
        "academic_hunter.interfaces.mcp.tools.obsidian.HunterConfig"
    ) as m:
        instance = m.return_value
        instance.settings = {"obsidian_vault_path": "/tmp/obsidian_test_vault"}
        yield instance


@pytest.fixture
def mock_mcp_db():
    """Mock ``MCPDatabaseManager`` for config-history tests."""
    with patch(
        "academic_hunter.interfaces.mcp.tools.configuration.MCPDatabaseManager"
    ) as m:
        instance = m.return_value
        instance.save_config.return_value = None
        instance.list_configs.return_value = [
            {"id": 1, "timestamp": "2025-01-01", "topic": "Backup 1"}
        ]
        instance.get_config.return_value = {
            "settings": {"start_year": 2021},
            "anchors": {},
            "tech_strings": {},
            "tech_weights": {"term": 3.0},
            "context_rules": {},
            "keyword_only_terms": [],
            "keyword_only_category": "",
        }
        yield instance
