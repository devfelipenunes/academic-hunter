"""Integration tests for the MCP server via stdio transport.

Marked with ``@pytest.mark.integration`` — excluded from default test
runs (use ``-m integration`` to run). Server startup is slow (~11s due to
Chromadb/sentence-transformers imports).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SRC_DIR = str(PROJECT_ROOT / "src")
ENV = {**os.environ, "PYTHONPATH": SRC_DIR, "PYTHONUNBUFFERED": "1"}
SERVER = [sys.executable, "-m", "academic_hunter.interfaces.mcp.server"]


def _send(requests: list[dict]) -> str:
    """Send JSON-RPC requests, return all stdout."""
    data = "\n".join(json.dumps(r) for r in requests) + "\n"
    proc = subprocess.Popen(
        SERVER, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, env=ENV, cwd=str(PROJECT_ROOT),
    )
    out, _ = proc.communicate(input=data.encode(), timeout=45)
    return out.decode()


def _find(stdout: str, expected_id: int) -> dict:
    """Extract JSON-RPC response by id from stdout."""
    for line in stdout.strip().split("\n"):
        try:
            data = json.loads(line)
            if data.get("id") == expected_id:
                return data
        except (json.JSONDecodeError, KeyError):
            continue
    pytest.fail(f"Response id={expected_id} not found.\nOutput preview:\n{stdout[:300]}")


_INIT = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05", "capabilities": {},
        "clientInfo": {"name": "test", "version": "1.0"},
    },
}
_NOTIF = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}


@pytest.mark.integration
def test_server_initialize():
    """Server responds to initialize with capabilities."""
    stdout = _send([_INIT])
    resp = _find(stdout, 1)
    assert resp["result"]["serverInfo"]["name"] == "academic-hunter"


@pytest.mark.integration
def test_list_tools():
    """Server returns at least 28 registered tools."""
    stdout = _send([_INIT, _NOTIF, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}])
    resp = _find(stdout, 2)
    tools = resp["result"]["tools"]
    names = {t["name"] for t in tools}
    for expected in ("run_search", "read_config", "server_status", "semantic_search",
                     "cluster_papers", "find_novel_papers", "summarize_paper",
                     "search_europepmc", "search_openaire", "lookup_orcid"):
        assert expected in names, f"Tool '{expected}' not found"
    assert len(tools) == 44, (
        f"Expected 44 tools, got {len(tools)}. A tool that loses its `Context` "
        f"annotation stops being discovered without an import error; if the "
        f"change was deliberate, update this number."
    )
