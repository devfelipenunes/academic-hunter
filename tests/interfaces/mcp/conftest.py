"""Shared fixtures for MCP tool tests.

All MCP test files import from here to ensure consistent mock patterns.
Uses pytest fixtures and unittest.mock throughout.
"""

import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from academic_hunter.core.infra.transport import HttpTransport
from academic_hunter.interfaces.mcp.cache import (
    citation_cache,
    discovery_cache,
    discovery_titles,
)
from academic_hunter.interfaces.mcp.tools import _utils


@pytest.fixture
def mock_ctx():
    """Standard mock for FastMCP Context.

    Auto-injected by FastMCP when a tool parameter is type-hinted as ``Context``.
    In unit tests we inject this mock directly.
    """
    ctx = AsyncMock()
    ctx.info = AsyncMock()
    ctx.error = AsyncMock()
    ctx.warning = AsyncMock()
    ctx.debug = AsyncMock()
    ctx.report_progress = AsyncMock()
    return ctx


@pytest.fixture
def mock_hunter():
    """Mock ``AcademicHunter`` so no real config, cache, or APIs are touched."""
    with patch("academic_hunter.interfaces.mcp.tools.search.AcademicHunter") as m:
        instance = m.return_value
        instance.run.return_value = "/tmp/dummy/report.md"
        yield instance


@pytest.fixture(autouse=True)
def _clear_mcp_caches():
    """Clear TTL caches before each test to avoid cross-test interference."""
    citation_cache.clear()
    discovery_cache.clear()
    discovery_titles.clear()


@pytest.fixture
def mock_openalex(monkeypatch):
    """Neutralise the OpenAlex transport: no config read, no waiting, no blocking.

    Three things. Reading the project's ``config.json`` for the credential would
    make a test depend on whichever file sits on the machine, so the headers and
    params come back empty. Waiting would hold every call for the source's delay
    — and now also for the retry backoff, which the MCP path did not have before
    it shared the pipeline's policy — so sleeps are dropped. And a *fresh*
    transport per test keeps a pacing escalation from one test out of the next:
    in production the instance is deliberately module-level, because pacing is
    about the session rather than the request.
    """
    transport = HttpTransport(
        lock=threading.Lock(),
        semaphore=threading.Semaphore(2),
        pacing_delays={},
        last_request_by_domain={},
        blocked_sources=set(),
        default_delay=0.0,
        block_sources=False,
        sleep=lambda seconds: None,
    )
    monkeypatch.setattr(_utils, "_openalex_transport", lambda: transport)
    monkeypatch.setattr(_utils, "_openalex_headers_and_params", lambda: ({}, {}))
    yield


@pytest.fixture
def openalex_work():
    """Build an OpenAlex `/works` record, with the abstract given as text.

    OpenAlex ships abstracts as ``{word: [positions]}``, so a test that wants to
    state one in prose goes through here instead of hand-building the index.
    """

    def _work(title, year, abstract="", **extra):
        index: dict = {}
        for position, word in enumerate((abstract or "").split()):
            index.setdefault(word, []).append(position)
        return {
            "display_name": title,
            "publication_year": year,
            "abstract_inverted_index": index or None,
            **extra,
        }

    return _work


@pytest.fixture
def openalex_response():
    """A mocked ``requests`` response carrying an OpenAlex JSON payload."""

    def _response(payload, status_code=200):
        response = MagicMock()
        response.status_code = status_code
        response.json.return_value = payload
        return response

    return _response


@pytest.fixture
def mock_hunter_rag():
    """Mock ``AcademicHunter`` specifically for RAG tool tests."""
    with patch("academic_hunter.interfaces.mcp.tools._utils.AcademicHunter") as m:
        yield m.return_value


@pytest.fixture
def mock_vector_store():
    """Mock ``_get_vector_store``."""
    with patch(
        "academic_hunter.interfaces.mcp.tools.rag._get_vector_store"
    ) as m:
        instance = MagicMock()
        instance.query.return_value = []
        instance.collection_stats.return_value = {"count": 0}
        instance.list_collections.return_value = []
        instance.index_papers.return_value = True
        instance.default_collection = "papers"
        m.return_value = instance
        yield instance


@pytest.fixture
def mock_hunter_config():
    """Mock ``HunterConfig`` for configuration tool tests."""
    with patch(
        "academic_hunter.core.infra.config.HunterConfig"
    ) as m:
        instance = m.return_value
        instance.settings = {"start_year": 2020, "limit_per_query": 100}
        instance.public_settings = MagicMock(return_value=dict(instance.settings))
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
        "academic_hunter.core.infra.config.HunterConfig"
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
