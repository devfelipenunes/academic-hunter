"""Tests for the server_status tool and health check.

Validates that:
- server_status returns meaningful data when everything is healthy.
- server_status handles missing components gracefully.
- The JSON response contains expected keys.
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from academic_hunter.interfaces.mcp.exceptions import ConfigError


# ── Fixtures patching the correct import paths ─────────────────────────────────


@pytest.fixture
def mock_config_ok():
    """HunterConfig loads without error (patched at its real import path)."""
    with patch("academic_hunter.core.infra.config.HunterConfig") as m:
        inst = m.return_value
        inst.settings = {"start_year": 2020, "limit_per_query": 100}
        yield inst


@pytest.fixture
def mock_config_fail():
    """HunterConfig raises when instantiated."""
    with patch("academic_hunter.core.infra.config.HunterConfig") as m:
        m.side_effect = ConfigError("config.json not found")
        yield m


@pytest.fixture
def mock_chroma_ok():
    """ChromaVectorStore returns data."""
    with patch("academic_hunter.plugins.vector_stores.ChromaVectorStore") as m:
        inst = m.return_value
        inst.collection_stats.return_value = {"count": 42}
        inst.list_collections.return_value = ["papers"]
        yield inst


@pytest.fixture
def mock_chroma_fail():
    """ChromaVectorStore raises when instantiated."""
    with patch("academic_hunter.plugins.vector_stores.ChromaVectorStore") as m:
        m.side_effect = RuntimeError("ChromaDB unreachable")
        yield m


@pytest.fixture
def mock_db_ok():
    """MCPDatabaseManager returns config history."""
    with patch(
        "academic_hunter.interfaces.mcp.memory.config_backup.MCPDatabaseManager"
    ) as m:
        inst = m.return_value
        inst.list_configs.return_value = [
            {"id": 1, "timestamp": "2025-01-01", "topic": "Test Config"}
        ]
        yield inst


@pytest.fixture
def mock_db_fail():
    """MCPDatabaseManager raises (non-critical — handled silently)."""
    with patch(
        "academic_hunter.interfaces.mcp.memory.config_backup.MCPDatabaseManager"
    ) as m:
        m.side_effect = RuntimeError("DB unreachable")
        yield m


# ── server_status tool tests ──────────────────────────────────────────────────


class TestServerStatusTool:
    """Tests for the server_status MCP tool."""

    async def test_returns_healthy_status(
        self, mock_config_ok, mock_chroma_ok, mock_db_ok, mock_ctx
    ):
        from academic_hunter.interfaces.mcp.server import server_status

        result = await server_status(mock_ctx)
        data = json.loads(result)

        assert data["status"] == "ok"
        assert data["config_loaded"] is True
        assert data["vector_store"]["available"] is True
        assert data["vector_store"]["paper_count"] == 42
        assert data["last_config_backup"] == "2025-01-01"

    async def test_handles_config_failure(
        self, mock_config_fail, mock_chroma_ok, mock_db_ok, mock_ctx
    ):
        from academic_hunter.interfaces.mcp.server import server_status

        result = await server_status(mock_ctx)
        data = json.loads(result)

        assert data["status"] == "degraded"
        assert data["config_loaded"] is False
        assert data["vector_store"]["available"] is True

    async def test_handles_chroma_failure(
        self, mock_config_ok, mock_chroma_fail, mock_db_ok, mock_ctx
    ):
        from academic_hunter.interfaces.mcp.server import server_status

        result = await server_status(mock_ctx)
        data = json.loads(result)

        assert data["status"] == "degraded"
        assert data["vector_store"]["available"] is False
        assert data["vector_store"]["paper_count"] == 0

    async def test_handles_everything_failing(
        self, mock_config_fail, mock_chroma_fail, mock_db_fail, mock_ctx
    ):
        from academic_hunter.interfaces.mcp.server import server_status

        result = await server_status(mock_ctx)
        data = json.loads(result)

        assert data["status"] == "error"
        assert data["config_loaded"] is False
        assert data["vector_store"]["available"] is False

    async def test_logs_calls(self, mock_config_ok, mock_chroma_ok, mock_db_ok, mock_ctx):
        from academic_hunter.interfaces.mcp.server import server_status

        await server_status(mock_ctx)

        mock_ctx.info.assert_any_call("Checking server status...")
        mock_ctx.info.assert_any_call("Server status: ok")

    async def test_db_failure_non_critical(
        self, mock_config_ok, mock_chroma_ok, mock_db_fail, mock_ctx
    ):
        """DB failure should not affect overall status — treated as best-effort."""
        from academic_hunter.interfaces.mcp.server import server_status

        result = await server_status(mock_ctx)
        data = json.loads(result)

        # Status remains ok because config and vector store work
        assert data["status"] == "ok"
        assert data["last_config_backup"] is None


# ── /health HTTP route tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
class TestHealthRoute:
    """Tests for the /health custom HTTP route (async)."""

    async def test_health_returns_json(
        self, mock_config_ok, mock_chroma_ok, mock_db_ok
    ):
        from academic_hunter.interfaces.mcp.server import health_check

        request = MagicMock()
        response = await health_check(request)

        assert response.status_code == 200
        data = json.loads(response.body)
        assert data["status"] == "ok"
        assert data["server"] == "academic-hunter"

    async def test_health_degraded(
        self, mock_config_fail, mock_chroma_ok, mock_db_ok
    ):
        from academic_hunter.interfaces.mcp.server import health_check

        request = MagicMock()
        response = await health_check(request)

        assert response.status_code == 200
        data = json.loads(response.body)
        assert data["status"] == "degraded"
