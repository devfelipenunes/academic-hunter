# MCP Server Setup Guide

The Model Context Protocol (MCP) lets an AI agent drive the Academic Hunter
engine directly: run searches, explore the citation graph, analyse the corpus
and export the results.

This is the canonical guide. `README.md` and `docs/tutorial.md` link here rather
than repeating it, because the copies drifted apart the last four times the
install changed.

## 1. Install first

No clone and no virtualenv: `uvx` builds the environment from the published
package. Three commands, in this order.

```bash
# 1. uv, once per machine
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Warm the cache — this is where the download happens
uvx --from 'academic-hunter[fulltext]' academic-mcp --help

# 3. Register it (user scope: connects without an approval prompt)
claude mcp add --scope user academic-hunter -- \
  uvx --from 'academic-hunter[fulltext]' academic-mcp
```

**Step 2 is not optional.** Skip it and the *client* runs `uvx` for the first
time, inside its own spawn, with no progress bar — while it fetches the
dependencies, **439 MB measured**. Clients give up long before that finishes, and
report it as a generic `failed to connect`.

One more download is possible, and the client would be waiting on it too:
ChromaDB's embedding model, **79 MB measured**, into
`~/.cache/chroma/onnx_models/`. It is built lazily, on the first operation that
actually embeds — measured twice, a search on the default config did **not**
trigger it, so this is not a step to warm. When it does fire it fires inside the
client, with the same silent wait as step 2.

`--from '<distribution>[extras]' <script>` is required, not decoration: the
distribution is `academic-hunter` and the console script is `academic-mcp`, so
the bare name resolves to nothing.

`ml` is optional, and the search does not need it. The semantic screener embeds
with ChromaDB's ONNX model, which comes with the base install, so scoring,
ranking and indexing work without it. What `ml` adds is `sentence-transformers`,
`scikit-learn`, `umap-learn`, `bertopic` and `hdbscan`, for the analysis tools:
clustering, landscape and evolution visualisation, semantic deduplication,
novelty detection and abstract summarization. Without it those tools return a
message naming this extra — they do not fail silently, and nothing else changes.
Adding it costs **3.15 GB measured** (about 2.5 GB of that is the CUDA build and
the NVIDIA runtime, which a CPU-only machine never loads); to add it, use
`'academic-hunter[ml,fulltext]'`.

### From a clone, for development

```bash
git clone https://github.com/devfelipenunes/academic-hunter.git
cd academic-hunter

python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -e ".[fulltext]"
```

Add the analysis extras — clustering, visualisation, deduplication, novelty,
summarization — with `pip install -e ".[ml,fulltext]"`; that is the 3.15 GB
download.

`python install.py` does all of the above, writes the client config for you
(with this checkout's real path) and then starts the server to confirm it
answers. `--ml` adds the analysis extras.

## 2. Point a client at it

With `uvx` there is nothing to point at: no path, no virtualenv, no placeholder
to fill in. Every client needs the same two strings.

```json
{
  "mcpServers": {
    "academic-hunter": {
      "command": "uvx",
      "args": ["--from", "academic-hunter[fulltext]", "academic-mcp"]
    }
  }
}
```

> [!IMPORTANT]
> A **project-scoped** `.mcp.json` is not loaded until you approve it in an
> interactive session — Claude Code offers it as `⏸ Pending approval`, and a
> cloned repository cannot approve its own servers. That gate is deliberate and
> this guide does not work around it.
>
> So on Claude Code, register at **user** scope instead: `claude mcp add --scope
> user` writes to `~/.claude.json`, which connects without a prompt. Use project
> scope only when you want the server to travel with a checkout.

### From a clone, for development

Every client needs the **absolute path to the console script inside the
virtualenv**:

```json
{
  "mcpServers": {
    "academic-hunter": {
      "command": "/absolute/path/to/academic-hunter/venv/bin/academic-mcp",
      "args": ["--transport", "stdio"]
    }
  }
}
```

> [!IMPORTANT]
> Not a bare `academic-mcp`. A client starts the server without activating any
> environment, so the bare name is resolved against the *client's* `PATH` — and
> when it is not found, the only symptom is the same generic `failed to connect`.
> There is also no `PYTHONPATH` to set: an editable install already resolves the
> package.
>
> The versioned `.mcp.json.example` and `.codex/config.toml.example` carry a
> placeholder path for exactly this reason; the real configs are generated and
> are not tracked.

### Claude Code

User scope — the server is available in every directory and connects with no
prompt. This is the command from §1 step 3:

```bash
claude mcp add --scope user academic-hunter -- \
  uvx --from 'academic-hunter[fulltext]' academic-mcp

claude mcp list
```

`claude mcp list` should report it **connected**. A `⏸ Pending approval` there
means it was registered at project scope instead, where the prompt is waiting.

Project scope, so the server travels with the checkout instead:

```bash
python install.py          # writes .mcp.json
```

Then restart Claude Code in this directory and **approve** the server when it is
offered — a project-scoped server is not loaded until you do. The approval prompt
is a deliberate safety gate against a `.mcp.json` arriving with a third-party
repository, so `install.py` does not disable it.

### Claude Desktop

Add the `uvx` block from §2 to `claude_desktop_config.json` and restart:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux:** `~/.config/Claude/claude_desktop_config.json` (not officially supported)

`install.py` can write it for you; it asks before doing so.

### Cursor

**Settings > Features > MCP > Add Server > command**, name `academic-hunter`, and
use the `command` and `args` from §2 verbatim — `uvx` and the three arguments.

### Codex

```toml
[mcp_servers.academic-hunter]
command = "uvx"
args = [
    "--from",
    "academic-hunter[fulltext]",
    "academic-mcp",
]
```

From a clone instead, `.codex/config.toml` in the repository root takes the
virtualenv's absolute path; `install.py` generates it that way, and the versioned
template is `.codex/config.toml.example`:

```toml
[mcp_servers.academic-hunter]
command = "/absolute/path/to/academic-hunter/venv/bin/academic-mcp"
args = [
    "--transport",
    "stdio",
]
```

### Anything else over HTTP

For a remote agent or a container, run the server in SSE mode instead. See
[the MCP reference](mcp/index.html) for `ACADEMIC_MCP_TRANSPORT`,
`ACADEMIC_MCP_HOST`, `ACADEMIC_MCP_PORT` and the `GET /health` endpoint.

## 3. Confirm it works

Connected, the agent sees 44 tools.

The first tool call is also where a config problem shows up, so it is worth
asking the server what it resolved before running anything else:

> *"Call read_config and tell me the `config_source`."*

That reports the file it read, which rung of the search order chose it, and
whether it fell back to the packaged default. A `packaged_default` there means no
config was found: the server runs, but with no anchors, so `run_search` refuses —
the pipeline queries once per anchor, and with none it would ask nothing at all.
The refusal names the file, so the fix is `quick_topic_discovery` and then
`update_config`.

Without a client, the cheapest check is to start the server with stdin already
closed and see how it exits:

```bash
uvx --from 'academic-hunter[fulltext]' academic-mcp --transport stdio < /dev/null
echo $?          # 0, and nothing on stdout
```

That only proves it starts. `install.py` goes further and runs a real
`initialize` + `tools/list` handshake, then prints the tool count — which is the
check that catches the failure `pyproject.toml` warns about, where a bad `mcp`
version makes the server exit silently and cleanly, installed and still useless.

## 4. Using the agent profiles

To get the most out of the integration, copy the prompts in
[`docs/superpowers/agents/`](superpowers/agents/) into your agent's system prompt
or project instructions.

These profiles (`01_orchestrator`, `02_hunter`, `03_synthesizer`) give the model
strict rules on how to chain the MCP tools together.
