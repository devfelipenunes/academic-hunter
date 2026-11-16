<div align="center">
  <h1>🎯 Academic Hunter</h1>
  <p><b>Automated Systematic Literature Reviews with Semantic Intelligence</b></p>

[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/github/license/devfelipenunes/academic-hunter)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/github/actions/workflow/status/devfelipenunes/academic-hunter/test.yml?branch=main&label=tests)](https://github.com/devfelipenunes/academic-hunter/actions)
[![MCP Ready](https://img.shields.io/badge/Protocol-MCP_Ready-orange.svg)](https://modelcontextprotocol.io/)
</div>

Academic Hunter is an open-source Systematic Literature Review (SLR) tool that combines **multi-source search** (six databases queried in parallel, twelve reachable in total), **semantic relevance scoring** (Weight-Bleeding), **topic clustering** (BERTopic), **novelty detection**, **extractive summarization**, and a **Model Context Protocol (MCP) server** — all running locally on CPU, with zero API costs.

---

## 🚀 Quickstart: your first SLR in a minute

Academic Hunter is an **MCP server**: connect it to an AI agent and ask for the review in plain language.

```bash
# 1. uv, once per machine
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Warm the cache HERE, outside the client — this is the step that downloads
#    the 439 MB (measured). If the client does it instead, it waits with no
#    progress bar and gives up with a generic "failed to connect".
uvx --from 'academic-hunter[fulltext]' academic-mcp --help

# 3. Register it with Claude Code (user scope: connects without an approval prompt)
claude mcp add --scope user academic-hunter -- \
  uvx --from 'academic-hunter[fulltext]' academic-mcp
```

No clone, no virtualenv, no absolute path. The `--from` is not decoration: the distribution is called `academic-hunter` and the console script is called `academic-mcp`, so the bare name resolves to nothing.

For other clients — Claude Desktop, Codex, Cursor — use `uvx` as the `command` and `["--from", "academic-hunter[fulltext]", "academic-mcp"]` as the `args` in place of the §2 block of the [MCP connection guide](https://github.com/devfelipenunes/academic-hunter/blob/main/docs/mcp_setup.md).

The server starts with no configuration at all, on a neutral default, and says so in its log. The first thing to ask the agent is the topic:

> _"Do a review on X."_

The agent starts with `quick_topic_discovery`, which returns the most relevant titles and the terms those titles use, counted. **No configuration comes with it:** the anchors and technical terms are written by the agent from that vocabulary. It applies them with `update_config` and runs `run_search`.

Without anchors, `run_search` refuses to run — instead of querying every source for nothing and reporting success. Without `technical_strings` it runs, but warns which sources it left out: the four that query by anchor × technical term are never called, and their `0` in the report is not a result.

To check before a run, `update_config`'s reply says what the configuration will query, and `run_search`'s says what was actually queried.

### Before your first search: API keys

arXiv, Crossref and DOAJ work with no credentials. **OpenAlex needs a free API key for this connector's cursor paging beyond the first page**; without it the source is reported as *not queried*, rather than returning a `0` that reads like an empty result. See [OpenAlex authentication and paging](https://help.openalex.org/api/authentication/).

Semantic Scholar and CORE also need a key:

| Source | Key | Where to get it |
| --- | --- | --- |
| **Semantic Scholar** | `SEMANTIC_SCHOLAR_API_KEY` or `settings.api_keys.semantic_scholar` | Free, from the [Semantic Scholar API page](https://www.semanticscholar.org/product/api). Without it the shared pool rate-limits the run a few requests in. |
| **CORE** | `CORE_API_KEY` or `settings.api_keys.core` | Free for research, from [core.ac.uk/services/api](https://core.ac.uk/services/api). The endpoint answers 401 without one. |
| **OpenAlex** | `OPENALEX_API_KEY` or `settings.api_keys.openalex` | Free key from [OpenAlex](https://openalex.org/); required to page beyond the first results page. |

These keys are optional — the report names any sources it did not query. `settings.api_keys.lens` is separate: `search_source(source="lens")` cannot run without a Lens.org token either.

<details>
<summary>Install from a clone (development)</summary>

```bash
# `ml` is optional: search works without it, and the analysis tools say so by
# name. `fulltext` is the documented default extra.
pip install -e ".[fulltext]"

# Start the MCP server (stdio)
academic-mcp

# Or in HTTP (SSE) mode for remote access
academic-mcp -t sse --host 0.0.0.0 --port 8080
```

`python install.py` does all of the above, writes the client config with this checkout's path, and confirms the server answers.

</details>

Once connected, just ask — _"run a systematic review on X"_ — and the agent orchestrates the tools (`run_search`, `semantic_search`, `cluster_papers`).

## 📖 Tutorial

See the [step-by-step tutorial](https://github.com/devfelipenunes/academic-hunter/blob/main/docs/tutorial.md) — ten minutes to your first complete SLR.

---

## ✨ What it does

### 🔍 Multi-source search

The pipeline queries **six academic sources in parallel**: arXiv, Crossref and DOAJ without credentials, plus OpenAlex, Semantic Scholar and CORE when their keys are configured (see [above](#before-your-first-search-api-keys)). Everything found is deduplicated across sources.

A further six sources are reachable one at a time through MCP tools: OpenCitations, Unpaywall, Lens.org, OpenAIRE, ORCID and DataCite. Three of them are one tool with a `source` argument — `search_source` — because searching one source is one operation, and peers of `run_search` in the tool list are how an agent comes to pick one of them instead of the review.

Europe PMC, bioRxiv and medRxiv are deliberately not among them: they index medicine and the life sciences, and no review this tool is used for is in those fields. Europe PMC is still read from, by the full-text step — that is a way of getting the text of a paper rather than a collection to search, and it is the only one that needs neither the `fulltext` extra nor an open-access PDF.

### 🧠 Weight-Bleeding scoring

An original method for configurable semantic weighting: a weighted centroid in embedding space lets you say which terms matter more, without touching the model, without a GPU and without labelled data.

### 📊 What you can ask of the corpus

Titles and abstracts are embedded by one model — `all-MiniLM-L6-v2`, 22M parameters, about 79 MB to download (measured) and loaded once.

| Analysis | MCP tool | What it does |
| --- | --- | --- |
| Semantic search | `semantic_search` | Finds papers by CONCEPT, not by exact word |
| Re-ranking | `rerank_search` | Bi-encoder plus cross-encoder, for precision |
| Clustering | `cluster_papers` | Groups by topic automatically (BERTopic) |
| Outliers | `find_novel_papers` | Finds novel or disruptive papers |
| Snowballing | `find_related_papers` | "More like this" for a given paper |
| Topics | `trending_topics` | Identifies the most frequent subjects |
| Evolution | `topic_evolution` | Shows how subjects change across years |
| Duplicates | `semantic_dedup` | Finds duplicates by embedding similarity |
| Summaries | `summarize_paper` | Extractive summary via MMR |
| Inside a paper | `chunk_search` | Searches the full text, with section and offsets |

`answer_question` now prefers indexed full-text passages and returns evidence IDs with DOI, section, page range when available, and character offsets. If full text is not indexed, it falls back to retrieved abstract excerpts and labels that limitation. It packages evidence for the connected agent; it does not claim that a generated synthesis has been verified against the papers.

Two more analyses the table used to mix in with these do **not** use the model — they are single HTTP lookups: `get_citation_count` (OpenCitations) and `find_open_access` (Unpaywall).

### 🤖 MCP server — agent integration

Academic Hunter exposes **39 tools, 3 resources plus one URI template, and 2 prompts** over the Model Context Protocol. Any AI agent (Claude, ChatGPT, LangChain) can orchestrate a complete systematic review on its own.

The tools are not one flat list, and the server tells a connecting agent which is which:

| Group | Count | What it is |
| --- | --- | --- |
| **Pipeline** | 4 | `quick_topic_discovery` → `update_config` → `run_search` → `read_latest_report`. This is the review. |
| **On-demand lookups** | 8 | Bypassing the pipeline: no run, no report. `search_source` queries one of six external sources per call, and seven more tools answer about one record — an open-access copy, an ORCID profile, a citation count, a DOI, a citation graph. For the specific thing the user asked about. |
| **Support** | 27 | Everything over the corpus a run produced: the analyses above, export, full text, configuration and health. |

Launch commands are in the table below, and each client's connection is in the [MCP connection guide](https://github.com/devfelipenunes/academic-hunter/blob/main/docs/mcp_setup.md) — the README repeats neither.

### 📦 Multi-format export

Every run writes **CSV, BibTeX, RIS, Markdown and PRISMA** artifacts into its own directory, plus `screening_candidates_*.csv` with every paper that passed year and anchor checks, and `screening_exclusions_*.csv` with unique papers rejected at the year/anchor stage. Both screening files include the automatic reason and blank columns for human adjudication, preserving candidates for recall audits. **Obsidian** notes are written on request. `export_report` additionally offers **JSON**, for pulling the included rows out of the latest run.

### Retrieval evaluation

The evaluation harness accepts either a saved run directory or a direct CSV. `tests/evaluation/qrels_microplastics_known_item_seed.json` is a small known-item retrieval seed for the freshwater microplastics review. Its target pairs come from the current AI-adjudicated matrix and are **not human gold labels**; validate them before using scores as evidence of scientific relevance. Example:

```bash
uv run python tests/evaluation/harness.py \
  --dataset research/microplastics-freshwater/consolidated-adjudication-round3.csv \
  --qrels tests/evaluation/qrels_microplastics_known_item_seed.json \
  --weights 1,0
```

Initial BM25, dense, and hybrid measurements are recorded in [`microplastics-seed-baseline-20261116.md`](tests/evaluation/microplastics-seed-baseline-20261116.md), with the same warning about provisional labels.
The ten known-item article titles and question claims were checked by AI against publisher or institutional source pages; [`microplastics-source-validation-20261116.md`](tests/evaluation/microplastics-source-validation-20261116.md) records the evidence. Human validation is still pending in [`qrels_microplastics_known_item_review.csv`](tests/evaluation/qrels_microplastics_known_item_review.csv).
For a broader ranking stress test, [`microplastics_relevance_pool_seed.json`](tests/evaluation/microplastics_relevance_pool_seed.json) contains five queries and 60 provisional AI grades over 44 unique papers. These are not gold labels. Review or replace the grades in [`microplastics_relevance_pool_review.csv`](tests/evaluation/microplastics_relevance_pool_review.csv) before using pool scores to compare ranking quality. The harness reports the annotation status with every pool result.

The architectural decision on LangChain/LangGraph is recorded in [`docs/adr/0001-agent-orchestration.md`](docs/adr/0001-agent-orchestration.md): they remain optional integrations until a concrete long-running, resumable human-review workflow justifies graph orchestration.

---

## 🔧 Commands

| Command | Description |
| --- | --- |
| `academic-mcp` | Start the MCP server (stdio) |
| `academic-mcp -t sse` | Start the MCP server in HTTP mode |

---

## 📊 Compared with existing tools

| Feature | Academic Hunter | ASReview | Rayyan | Covidence |
| --- | --- | --- | --- | --- |
| Open source | ✅ | ✅ | ❌ | ❌ |
| Data sources | **15** | 1 (import) | 1 | 1 |
| Semantic scoring | ✅ Weight-Bleeding | ❌ | ❌ | ❌ |
| Automatic clustering | ✅ | ❌ | ❌ | ❌ |
| Novelty detection | ✅ | ❌ | ❌ | ❌ |
| MCP / API for AI | ✅ | ❌ | ❌ | ❌ |
| Offline-first | ✅ | ✅ | ❌ | ❌ |
| Cost | **Zero** | Zero | $$$ | $$$$ |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│               MCP Server (39 tools, stdio)                  │
│      3 Resources · 1 URI Template · 2 Prompts · /health     │
├─────────────────────────────────────────────────────────────┤
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│ │  Search  │ │  NLP     │ │  MCP     │ │  Exporters       │ │
│ │  6 APIs  │ │  Scorer  │ │  Tools   │ │  CSV/Bib/RIS/MD  │ │
│ └──────────┘ └──────────┘ └──────────┘ └──────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

`academic-mcp` speaks stdio by default; `-t sse` switches it to HTTP for remote access. The layout is hexagonal — ports in `core/`, adapters in `plugins/`, entry points in `interfaces/` — and [docs/architecture.md](https://github.com/devfelipenunes/academic-hunter/blob/main/docs/architecture.md) has the diagram.

---

## 📚 Publications

- **JOSS**: "Academic Hunter: An Open-Source Systematic Literature Review Tool with Agentic RAG and Embedding-Space Relevance Scoring"
- **Conference**: "Weight-Bleeding: Configurable Semantic Relevance Scoring via Input-Level Term Repetition in Bi-Encoders"

The manuscripts do not ship with this repository, which publishes the software only.

---

## 📄 License

MIT License — use it, change it, distribute it freely.

## 🤝 Contributing

Issues, pull requests and feedback are welcome — see [CONTRIBUTING.md](https://github.com/devfelipenunes/academic-hunter/blob/main/CONTRIBUTING.md).
