"""Tests for the server_status tool and health check.

Validates that:
- server_status returns meaningful data when everything is healthy.
- server_status handles missing components gracefully.
- The JSON response contains expected keys.
- server_status says *which* code is running and which extras it can import.
"""

import importlib.metadata
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from academic_hunter.interfaces.mcp.exceptions import ConfigError


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
    """_get_vector_store returns a working vector store."""
    with patch("academic_hunter.interfaces.mcp.health._get_vector_store") as m:
        inst = MagicMock()
        inst.collection_stats.return_value = {"count": 42}
        inst.list_collections.return_value = ["papers"]
        m.return_value = inst
        yield inst


@pytest.fixture
def mock_chroma_fail():
    """_get_vector_store returns None."""
    with patch(
        "academic_hunter.interfaces.mcp.health._get_vector_store",
        return_value=None,
    ):
        yield None


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

    async def test_the_tool_reports_which_code_is_running(
        self, mock_config_ok, mock_chroma_ok, mock_db_ok, mock_ctx
    ):
        """Every other field is identical between a stale wheel and this checkout.

        So the answer has to carry the one that is not: where the package was
        imported from, and what that interpreter can actually import.
        """
        from academic_hunter.interfaces.mcp.server import server_status

        data = json.loads(await server_status(mock_ctx))

        assert set(data["identity"]) == {
            "version",
            "python",
            "package_dir",
            "source",
            "checkout_root",
            "extras",
        }
        assert set(data["identity"]["extras"]) == {"fulltext", "ml"}

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

        assert data["status"] == "ok"
        assert data["last_config_backup"] is None


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


class TestIdentity:
    """`server_status` has to say which code is running.

    A wheel built eleven days before answered every call while the checkout's
    fixes sat unread on disk: same distribution version, same config resolution,
    same tool list. Nothing in any reply distinguished the two, so the only
    symptom was behaviour that made no sense.
    """

    def test_a_checkout_is_reported_as_a_checkout(self, tmp_path):
        """`checkout_root` walks up for a `pyproject.toml` — a wheel has none."""
        from academic_hunter.interfaces.mcp import health

        with patch.object(health.paths, "checkout_root", return_value=tmp_path):
            identity = health._identity()

        assert identity["source"] == "checkout"
        assert identity["checkout_root"] == str(tmp_path)

    def test_an_installed_copy_is_reported_as_installed(self):
        from academic_hunter.interfaces.mcp import health

        with patch.object(health.paths, "checkout_root", return_value=None):
            identity = health._identity()

        assert identity["source"] == "installed"
        assert identity["checkout_root"] is None

    def test_the_version_comes_from_the_distribution_metadata(self):
        """Not `__version__`: the question is what the *environment* installed."""
        from academic_hunter.interfaces.mcp import health

        expected = importlib.metadata.version("academic-hunter")

        assert health._identity()["version"] == expected

    def test_a_package_with_no_metadata_does_not_break_the_probe(self):
        """The probe is what an orchestrator polls; it may report, not raise."""
        from academic_hunter.interfaces.mcp import health

        with patch.object(
            importlib.metadata,
            "version",
            side_effect=importlib.metadata.PackageNotFoundError("academic-hunter"),
        ):
            assert health._identity()["version"] == "unknown"

    def test_it_names_the_directory_the_package_was_imported_from(self):
        """The absolute path is what a reader compares against the checkout."""
        import academic_hunter
        from academic_hunter.interfaces.mcp import health

        expected = str(Path(academic_hunter.__file__).resolve().parent)

        assert health._identity()["package_dir"] == expected

    def test_it_names_the_interpreter(self):
        import sys

        from academic_hunter.interfaces.mcp import health

        assert health._identity()["python"] == sys.executable


class TestExtrasReport:
    """A missing extra is why an analysis tool fails instead of answering.

    The live server ran without `ml`, so the five analysis tools raised
    `No module named 'sklearn'` — a message that names a dependency of a
    dependency and says nothing about the install being incomplete.
    """

    def test_a_missing_module_is_named_under_its_extra(self):
        from academic_hunter.interfaces.mcp import health

        with patch.object(health, "_module_available", return_value=False):
            extras = health._extras_report()

        assert extras["fulltext"] == {"available": False, "missing": ["pypdf"]}
        assert extras["ml"]["available"] is False
        assert set(extras["ml"]["missing"]) == {
            "sentence_transformers",
            "sklearn",
            "umap",
            "bertopic",
            "hdbscan",
        }

    def test_a_complete_extra_is_available(self):
        from academic_hunter.interfaces.mcp import health

        with patch.object(health, "_module_available", return_value=True):
            extras = health._extras_report()

        assert extras["ml"] == {"available": True, "missing": []}
        assert extras["fulltext"] == {"available": True, "missing": []}

    def test_one_missing_module_makes_the_whole_extra_unavailable(self):
        """Four of five is not a partial analysis — it is a broken one."""
        from academic_hunter.interfaces.mcp import health

        with patch.object(
            health, "_module_available", side_effect=lambda name: name != "hdbscan"
        ):
            extras = health._extras_report()

        assert extras["ml"] == {"available": False, "missing": ["hdbscan"]}
        assert extras["fulltext"]["available"] is True

    def test_an_unknown_extra_module_is_simply_missing(self):
        """`find_spec` raises for a name that is not an identifier at all."""
        from academic_hunter.interfaces.mcp import health

        with patch.object(health.importlib.util, "find_spec", side_effect=ValueError):
            assert health._module_available("not a module") is False

    def test_probing_asks_for_the_spec_and_never_imports(self):
        """`ml` is torch: importing it to answer a status call costs gigabytes.

        `find_spec` locates the module without executing it, so the probe stays
        as cheap as the rest of the health check.
        """
        from academic_hunter.interfaces.mcp import health

        with patch.object(
            health.importlib.util, "find_spec", return_value=object()
        ) as find_spec:
            assert health._module_available("torch") is True

        find_spec.assert_called_once_with("torch")
