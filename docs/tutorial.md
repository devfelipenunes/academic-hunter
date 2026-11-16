# Tutorial: your first SLR in 10 minutes

This tutorial walks you through a complete Systematic Literature Review with Academic Hunter — no JSON editing, no programming, no GPU.

## What you will learn

1. Install Academic Hunter
2. Run a complete SLR by talking to an AI agent
3. Explore the results with the automatic analyses
4. Export to the format you prefer

---

## 1. Installation

No clone and no virtualenv — `uvx` builds the environment from the published package.

```bash
# 1. uv, once per machine
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Warm the cache HERE, outside the client: this is the step that downloads the
#    439 MB (measured). Left to the client, it waits with no progress bar and
#    gives up with a generic "failed to connect".
uvx --from 'academic-hunter[fulltext]' academic-mcp --help

# 3. Register it with Claude Code (user scope: connects without an approval prompt)
claude mcp add --scope user academic-hunter -- \
  uvx --from 'academic-hunter[fulltext]' academic-mcp
```

The `--from` is not decoration: the distribution is called `academic-hunter` and the console script is called `academic-mcp`, so the bare name resolves to nothing. `fulltext` is the documented default extra; `ml` is optional — search works without it, and the tools that need it name the extra instead of failing silently. Adding it costs 3.15 GB (measured, of which ~2.5 GB is a CUDA build that a machine without a GPU never loads).

You do not need to create a `config.json`. The server starts on a neutral default and says in its log that no configuration was found; the topic is set through the agent. It starts with `quick_topic_discovery`, which returns the most relevant titles and the terms they use, counted — with no configuration at all — writes the anchors from that vocabulary and applies them with `update_config`.

Without anchors, `run_search` refuses to run rather than querying every source for nothing. Without `technical_strings` it runs and warns which sources it left out — the four that query by anchor × technical term are not called, and their `0` in the report is not a result.

### API keys for broader source coverage

arXiv, Crossref and DOAJ work without credentials. **OpenAlex** needs a free key for this connector's cursor paging beyond the first page; **Semantic Scholar** and **CORE** also need keys. Without a key, each source is reported as not queried instead of as a source that found nothing. Configure them under `settings.api_keys` in `config.json`, or use `OPENALEX_API_KEY`, `SEMANTIC_SCHOLAR_API_KEY` and `CORE_API_KEY`. See the [README](../README.md#before-your-first-search-api-keys) for key links and details.

<details>
<summary>Install from a clone (development)</summary>

```bash
# Clone the repository
git clone https://github.com/devfelipenunes/academic-hunter.git
cd academic-hunter

# Create a virtualenv and install
python3 -m venv venv
source venv/bin/activate
pip install -e ".[fulltext]"

# Optional: a config of your own, in place of the neutral default
cp config.example.json config.json
```

`config.example.json` is a **template, not a starting configuration**: its anchors read `term one`, `term two`. Replace them before searching, or let `quick_topic_discovery` and `update_config` write the configuration for you — which is the path this tutorial takes.

</details>

## 2. Using it over MCP (recommended)

Academic Hunter is an **MCP server** — the way to use it is to connect it to an AI agent. With `uvx`, that is step 3 above; from a clone:

```bash
academic-mcp          # stdio
academic-mcp -t sse   # HTTP/SSE, for remote access
```

Once connected, just ask in plain language:

> "Run a systematic review on Central Bank Digital Currencies and Financial Stability"

The agent orchestrates the tools: `quick_topic_discovery` discovers the field's jargon, `update_config` writes the configuration, `run_search` executes the search, and `cluster_papers` and `find_novel_papers` analyse the result.

## 3. Manual configuration

For fine control, edit `config.json`. The three sections that carry the topic are `anchors` (what the search is about), `technical_strings` (terms that qualify it) and `technical_weights` (how much each term pulls the ranking):

```json
{
  "anchors": {
    "Settlement": ["atomic settlement", "finality"],
    "CBDC": ["central bank digital currency"]
  },
  "technical_strings": {
    "Method": ["comparative analysis", "taxonomy"]
  },
  "technical_weights": {
    "atomic settlement": 5.0,
    "cbdc": 5.0,
    "finality": 3.0
  },
  "settings": {
    "start_year": 2020,
    "limit_per_query": 100,
    "user_email": "you@example.com"
  }
}
```

Note what is **not** here: the topic is not a key of its own. `anchors` is where a search's subject lives, and every anchor × technical-term pair is what the four source-specific connectors query with — so a configuration with `anchors` but no `technical_strings` is a narrower search than it looks, and `run_search` says so in its reply.

By default, `context_rules` can match in the title or abstract. For a narrow scope, set `settings.context_rules_title_only` to `true` to require that context in the title, and use `settings.context_exclude_title_terms` to reject titles containing out-of-scope terms such as `marine` or `coastal`. These stricter checks improve precision but can miss relevant papers whose titles omit the setting.

Then run the search through the connected agent — the `run_search` tool.

## 4. Deeper analyses (over MCP)

After a search you can use the MCP tools for deeper analysis. Start the MCP server:

```bash
uvx --from 'academic-hunter[fulltext]' academic-mcp
```

Four of the tools below need the optional `ml` extra — `trending_topics`, `cluster_papers`, `find_novel_papers`, `topic_evolution` and `summarize_paper` name it when it is missing, rather than returning nothing. The rest work on the base install.

Connect any MCP client — Claude Code, Claude Desktop, Cursor — and use the tools. The step-by-step for each client is in the [MCP connection guide](mcp_setup.md):

| Tool | What it is for | Example |
| --- | --- | --- |
| `semantic_search` | Find papers by concept | `semantic_search(query="CBDC banking implications", top_k=10)` |
| `trending_topics` | See the hot subjects | `trending_topics(min_papers=3)` |
| `cluster_papers` | Group by topic | `cluster_papers(top_k=500, min_cluster_size=5)` |
| `find_novel_papers` | Detect outliers | `find_novel_papers(top_k=200, contamination=0.1)` |
| `find_related_papers` | Semantic snowballing | `find_related_papers(query="CBDC financial stability")` |
| `topic_evolution` | Change over time | `topic_evolution(top_k=500)` |
| `semantic_dedup` | Duplicates by meaning | `semantic_dedup(threshold=0.88)` |
| `summarize_paper` | Summary of one paper | `summarize_paper(doi="10.1016/j.jfe.2023.01.001")` |
| `get_citation_count` | Citations of one paper | `get_citation_count(doi="10.1016/j.jfe.2023.01.001")` |

`get_citation_count` and `find_open_access` are the two in this family that do not touch the embedding model at all — each is a single lookup against one service.

### Full text: searching inside the papers

Everything up to here works on title plus abstract, which truncates method and results. Full text is **opt-in and off by default** — turn it on with `settings.fulltext.enabled: true` in `config.json`, or just ask the agent:

| Tool | What it is for | Example |
| --- | --- | --- |
| `fulltext_status` | How much full text the corpus has, and where it came from | `fulltext_status()` |
| `index_fulltext` | Download, extract and index the last run's papers | `index_fulltext(limit=20)` |
| `chunk_search` | Search a passage, not a paper | `chunk_search(query="how many annotators coded the corpus")` |

`chunk_search` answers what the abstract cannot — which dataset they used, how many annotators, what the method actually did — returning the passages grouped under their source paper, with the section and the offsets into the extracted text (there is no page number: a PDF has pages, Europe PMC's JATS source does not). It needs the `fulltext` extra, already included in the installation above; without it only Europe PMC can supply text, and `fulltext_status` says so.

## 5. A complete flow over MCP

With Claude Desktop connected to Academic Hunter, you can simply say:

> "Do a systematic review on the impact of CBDCs on financial stability"

The agent will:

1. Explore the topic with `quick_topic_discovery`
2. Write the configuration with `update_config`
3. Run the pipeline with `run_search`
4. Analyse the results with `semantic_search`, `cluster_papers`, `find_novel_papers`
5. Export to Obsidian with `export_to_obsidian`

## 6. Export

Over MCP:

```
export_report(format="csv")
export_report(format="bibtex")
export_report(format="ris")
export_report(format="json")
```

Every run also writes its own `academic_dataset_*.csv`, `.bib` and `.ris`, a Markdown report, the PRISMA flow, and `screening_candidates_*.csv` into its `results/run_*/` directory. The screening file keeps scored candidates below the automatic cut and includes blank columns for human decision and notes; use it to audit potential false negatives. `export_report` produces the same four formats for a path of your choosing — and the CSV, BibTeX and RIS it writes are the same bytes the run's own files carry, from the same renderer.

`json` is the one format only `export_report` offers: the run does not write one, because the CSV already carries every column.

## Next steps

- 📖 Read the [full README](https://github.com/devfelipenunes/academic-hunter#readme)
- 🐛 Report bugs at [github.com/devfelipenunes/academic-hunter/issues](https://github.com/devfelipenunes/academic-hunter/issues)
- ⭐ Contribute to the project on GitHub
