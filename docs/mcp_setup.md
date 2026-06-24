# MCP Server Setup Guide

The Model Context Protocol (MCP) allows Large Language Models to interact directly with the Academic Hunter engine, giving them the superpower to autonomously run DeSci searches, explore citation graphs, and save results directly to your Obsidian Second Brain.

## Connecting to Claude Desktop

If you use Claude Desktop, you can add Academic Hunter as a custom tool server.

1. Open your Claude Desktop configuration file:
   - **Mac:** `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

2. Add the `academic-hunter` server to the `mcpServers` object. Make sure to replace `/absolute/path/to/academic-hunter` with the actual path on your machine:

```json
{
  "mcpServers": {
    "academic-hunter": {
      "command": "/absolute/path/to/academic-hunter/venv/bin/python",
      "args": [
        "-m",
        "academic_hunter.interfaces.mcp.server"
      ],
      "env": {
        "PYTHONPATH": "/absolute/path/to/academic-hunter/src"
      }
    }
  }
}
```

3. Restart Claude Desktop. You will now see a "hammer" icon indicating that the tools are loaded.

## Connecting to Cursor IDE

Cursor natively supports MCP.

1. Go to **Settings > Features > MCP**.
2. Click **Add Server**.
3. Choose **command**.
4. Set the name to `academic-hunter`.
5. Set the command to: `/absolute/path/to/academic-hunter/venv/bin/python -m academic_hunter.interfaces.mcp.server`
6. Set the `PYTHONPATH` environment variable if prompted.

## Using the Multi-Agent Framework

To get the most out of the MCP integration, we highly recommend copying the Prompts found in `docs/superpowers/agents/` into your LLM's system prompt or project instructions.

These Agent Profiles (`01_orchestrator`, `02_hunter`, `03_synthesizer`) provide the AI with strict rules on how to chain the MCP tools together for maximum autonomy.
