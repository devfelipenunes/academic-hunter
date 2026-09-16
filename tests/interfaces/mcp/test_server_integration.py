"""Integration tests for the MCP server via stdio transport.

Marked with ``@pytest.mark.integration`` — excluded from default test
runs (use ``-m integration`` to run). Chromadb and sentence-transformers
are imported lazily, so startup is ~2s.
"""

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SRC_DIR = str(PROJECT_ROOT / "src")
ENV = {**os.environ, "PYTHONPATH": SRC_DIR, "PYTHONUNBUFFERED": "1"}
SERVER = [sys.executable, "-m", "academic_hunter.interfaces.mcp.server"]


def _send(requests: list[dict], wait_for_id: int, timeout: float = 45) -> str:
    """Send JSON-RPC requests, return stdout up to the answer to `wait_for_id`.

    stdin stays open until that answer arrives. Closing it is what tells the
    server to shut down, so closing it up front raced the reply: the server
    occasionally exited with `tools/list` still unanswered, which is what made
    this test flaky rather than failing outright.
    """
    data = "\n".join(json.dumps(r) for r in requests) + "\n"
    proc = subprocess.Popen(
        SERVER, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, env=ENV, cwd=str(PROJECT_ROOT),
    )
    lines: list[str] = []
    answered = threading.Event()

    def _drain() -> None:
        for raw in proc.stdout:
            text = raw.decode()
            lines.append(text)
            try:
                if json.loads(text).get("id") == wait_for_id:
                    answered.set()
            except json.JSONDecodeError:
                pass

    reader = threading.Thread(target=_drain, daemon=True)
    reader.start()
    try:
        proc.stdin.write(data.encode())
        proc.stdin.flush()
        answered.wait(timeout)
    finally:
        proc.stdin.close()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        reader.join(timeout=5)
    return "".join(lines)


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
    stdout = _send([_INIT], wait_for_id=1)
    resp = _find(stdout, 1)
    assert resp["result"]["serverInfo"]["name"] == "academic-hunter"


@pytest.mark.integration
def test_list_tools():
    """Server returns every registered tool."""
    stdout = _send(
        [_INIT, _NOTIF, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}],
        wait_for_id=2,
    )
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
