"""Integration tests for the MCP server via stdio transport.

Launches the server as a subprocess, communicates via JSON-RPC 2.0
over stdin/stdout, and verifies protocol-level behavior.

Marked with ``@pytest.mark.integration`` — excluded from default test runs
(use ``-m integration`` to run).
"""

import asyncio
import contextlib
import json
import os
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SRC_DIR = str(PROJECT_ROOT / "src")


@contextlib.asynccontextmanager
async def mcp_server():
    """Launch the MCP server and yield (proc, send, wait_for_response)."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m", "academic_hunter.interfaces.mcp.server",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "PYTHONPATH": SRC_DIR},
        cwd=str(PROJECT_ROOT),
    )

    async def read_line(timeout=8.0):
        return await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)

    async def send(req):
        proc.stdin.write(json.dumps(req).encode() + b"\n")
        await proc.stdin.drain()

    async def recv(expected_id, timeout=8.0):
        while True:
            raw = await read_line(timeout=timeout)
            data = json.loads(raw.decode().strip())
            if data.get("id") == expected_id:
                return data

    try:
        yield proc, send, recv
    finally:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_server_initialize():
    """Server responds to initialize with capabilities."""
    async with mcp_server() as (proc, send, recv):
        await send({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        })
        resp = await recv(1)
        caps = resp["result"]
        assert caps["protocolVersion"] == "2024-11-05"
        assert caps["serverInfo"]["name"] == "academic-hunter"
        assert "tools" in caps["capabilities"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_tools():
    """Server returns all registered tools."""
    async with mcp_server() as (proc, send, recv):
        # Initialize
        await send({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        })
        await recv(1)
        # Send initialized notification
        await send({
            "jsonrpc": "2.0", "method": "notifications/initialized",
            "params": {},
        })
        await asyncio.sleep(0.3)

        # List tools
        await send({
            "jsonrpc": "2.0", "id": 2, "method": "tools/list",
            "params": {},
        })
        resp = await recv(2)
        tools = resp["result"]["tools"]
        tool_names = {t["name"] for t in tools}

        # Core tools that should always be present
        assert "run_search" in tool_names
        assert "read_config" in tool_names
        assert "server_status" in tool_names
        assert "read_latest_report" in tool_names
        assert "semantic_search" in tool_names
        assert "export_to_obsidian" in tool_names
        assert "compare_papers" in tool_names
        assert "trending_topics" in tool_names
        assert "export_report" in tool_names
        assert "answer_question" in tool_names
        assert len(tools) >= 18


@pytest.mark.integration
@pytest.mark.asyncio
async def test_call_read_config():
    """Calling read_config returns valid JSON with config keys."""
    async with mcp_server() as (proc, send, recv):
        await send({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        })
        await recv(1)
        await send({
            "jsonrpc": "2.0", "method": "notifications/initialized",
            "params": {},
        })
        await asyncio.sleep(0.3)

        await send({
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "read_config", "arguments": {}},
        })
        resp = await recv(2)
        text = resp["result"]["content"][0]["text"]
        data = json.loads(text)
        assert "settings" in data
        assert "anchors" in data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_call_server_status():
    """Calling server_status returns JSON with status field."""
    async with mcp_server() as (proc, send, recv):
        await send({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        })
        await recv(1)
        await send({
            "jsonrpc": "2.0", "method": "notifications/initialized",
            "params": {},
        })
        await asyncio.sleep(0.3)

        await send({
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "server_status", "arguments": {}},
        })
        resp = await recv(2)
        text = resp["result"]["content"][0]["text"]
        data = json.loads(text)
        assert "status" in data
        assert data["server"] == "academic-hunter"
