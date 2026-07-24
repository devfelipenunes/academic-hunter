---
title: "Academic Hunter: An Open-Source Systematic Literature Review Tool with Agentic RAG and Embedding-Space Relevance Scoring"
tags:
  - Python
  - systematic literature review
  - sentence embeddings
  - centroid interpolation
  - MCP
  - information retrieval
authors:
  - name: Felipe Nunes
    orcid: 0000-0000-0000-0000
    affiliation: 1
affiliations:
  - name: Independent Researcher
    index: 1
date: 21 July 2026
bibliography: paper.bib
---

# Summary

Academic Hunter is an automated Systematic Literature Review (SLR) tool that combines keyword-based and semantic relevance scoring in a configurable hybrid pipeline. It connects to 16 academic databases and preprint servers (ArXiv, Crossref, OpenAlex, Semantic Scholar, CORE, DBLP, DOAJ, Europe PMC, OpenCitations, Unpaywall, Lens.org, OpenAIRE, ClinicalTrials.gov, bioRxiv, medRxiv, DataCite), deduplicates results across sources, scores papers using both exact keyword matching and weighted sentence embeddings, clusters results by topic, detects novel/outlier papers, generates extractive summaries, projects embeddings onto a 2D research landscape via UMAP, and exports results in CSV, BibTeX, RIS, Markdown, PRISMA, and JSON formats. The tool exposes a Model Context Protocol (MCP) server with 35+ tools, 4 resources, and 2 prompt templates, enabling Large Language Models and agentic workflows to interact with the review pipeline autonomously. The server supports both stdio and SSE transport for local and remote agent access.

# Statement of Need

Systematic Literature Reviews are a cornerstone of evidence-based research, but the screening phase — identifying relevant papers from thousands of candidates — remains labor-intensive. While tools such as ASReview [@asreview2020] use active learning to prioritize screening, they require manually labeled data to train classifiers. Commercial platforms like Rayyan and Covidence offer team collaboration but are closed-source, require web access, and lack programmable APIs. Most importantly, no existing tool exposes a standardized protocol (MCP) that LLM agents can invoke programmatically — limiting their integration into autonomous research workflows.

Academic Hunter fills this gap as the first open-source SLR tool that combines multi-source search (16 sources), configurable semantic relevance scoring, topic clustering, novelty detection, extractive summarization, research landscape visualization, and a Model Context Protocol (MCP) server for agentic integration:

| Feature                                   | Academic Hunter    | ASReview | Rayyan | Covidence |
| ----------------------------------------- | ------------------ | -------- | ------ | --------- |
| Open source (MIT)                         | ✅                 | ✅       | ❌     | ❌        |
| Zero-shot (no labeled data)               | ✅                 | ❌       | ✅     | ✅        |
| Multi-source API search (16 sources)      | ✅                 | ❌       | ❌     | ❌        |
| Semantic relevance scoring                | ✅ Weight-Bleeding | ❌       | ❌     | ❌        |
| MCP server (35+ tools, 4 resources)       | ✅                 | ❌       | ❌     | ❌        |
| Agentic RAG ready                         | ✅                 | ❌       | ❌     | ❌        |
| Topic clustering (BERTopic)               | ✅                 | ❌       | ❌     | ❌        |
| Novelty / outlier detection               | ✅                 | ❌       | ❌     | ❌        |
| Extractive summarization (centroid + MMR) | ✅                 | ❌       | ❌     | ❌        |
| Research landscape (UMAP 2D)              | ✅                 | ❌       | ❌     | ❌        |
| Semantic deduplication                    | ✅                 | ❌       | ❌     | ❌        |
| PRISMA auto-export                        | ✅                 | ❌       | ❌     | ✅        |
| SSE remote access                         | ✅                 | ❌       | ❌     | ❌        |
| Offline-first (no GPU, no API key)        | ✅                 | ✅       | ❌     | ❌        |
| BibTeX / RIS / CSV / JSON export          | ✅                 | ✅       | ✅     | ✅        |

**Weight-Bleeding.** At the core of our relevance scoring is embedding-space centroid interpolation, a novel technique that biases bi-encoder sentence embeddings toward high-weight technical terms without modifying the model or requiring GPU compute. The reference centroid $v_{ref}$ is computed as a weighted average of the base embedding and each technical term's embedding:

$$v_{ref} = \frac{v_{base} \cdot N_{base} + \sum_{i} e_{t_i} \cdot W_i}{N_{base} + \sum_{i} W_i}$$

where $N_{base}$ is the base reference length in terms, $e_{t_i}$ is the target term's embedding (computed once), and $W_i$ is the domain weight for that term. This is mathematically equivalent to mean pooling over repeated tokens — a term with weight $W$ contributes $W$ times its embedding to the centroid — but computed directly in embedding space.

The final semantic relevance score is obtained by applying a non-linear transformation to the cosine similarity $\sigma \in [0, 1]$ between the paper embedding and the weighted centroid:

$$s_{sem} = \sqrt{\sigma} \times 10$$

The square root decompresses the lower range of cosine similarities, which in bi-encoders tends to cluster in a narrow band (~0.05--0.50 for tangentially related papers). This prevents relevant papers from being discarded by an overly aggressive threshold while preserving ranking order (the transform is monotonic — Spearman $\rho = 1.0$ against the linear baseline). We evaluated six alternative transformations (linear, cube root, log1p, quadratic, sigmoid-scaled) and found square root offers the best balance between recall and selectivity without introducing artificial thresholding artifacts.

This achieves configurable semantic weighting without modifying the model, training a cross-encoder, incurring GPU cost, or creating artificially repetitive input strings.

# Architecture

Academic Hunter follows a hexagonal architecture:

```
┌─────────────────────────────────────────────────────────────────┐
│                    MCP Server (35+ tools)                        │
│  4 Resources: config, reports, stats, papers                     │
│  2 Prompts: systematic-review, quick-discovery                   │
│  Health check: server_status(), /health (SSE)                    │
│  Transport: stdio, SSE (-t sse --host --port)                    │
├─────────────────────────────────────────────────────────────────┤
│  Core Tools    │  MiniLM Features    │  Connectors               │
│  run_search    │  cluster_papers     │  Europe PMC, OpenCitations│
│  semantic_srch │  find_novel_papers  │  Unpaywall, Lens.org      │
│  read_config   │  find_related       │  OpenAIRE, ClinicalTrials │
│  update_config │  trending_topics    │  bioRxiv, medRxiv, ORCID  │
│  compare_paper │  topic_evolution    │  DataCite, arXiv, S2, ... │
│  export_report │  semantic_dedup     │                           │
│  rerank_search │  visualize_landscape│                           │
│  summarize_ppr │  rerank_search      │                           │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                       Core Domain                               │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌──────────┐      │
│  │  Paper   │  │  NLP      │  │ Pipeline │  │  PRISMA  │      │
│  │  Model   │  │  Scorer   │  │  Manager │  │  Export  │      │
│  └──────────┘  └───────────┘  └──────────┘  └──────────┘      │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                      Plugin Layer                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐    │
│  │Connectors│  │Screeners │  │Exporters │  │VectorStore │    │
│  │16 sources│  │Keyword   │  │CSV,BibTeX│  │ ChromaDB   │    │
│  │          │  │Semantic  │  │RIS,MD,JSON│ │ (MiniLM)   │    │
│  └──────────┘  └──────────┘  └──────────┘  └────────────┘    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                    Infrastructure                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ SQLite   │  │ ChromaDB │  │ Config   │  │ Env Var  │      │
│  │  Cache   │  │  Vector  │  │  JSON    │  │Override  │      │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘      │
└─────────────────────────────────────────────────────────────────┘
```

Academic Hunter occupies a dual architectural role. **As a standalone SLR pipeline**, it performs multi-source search, domain-specific NLP filtering, Weight-Bleeding scoring, deduplication, and PRISMA-compliant export — all without requiring an LLM. **As an MCP tool server**, it exposes 15 retrieval tools that external LLM agents (Claude, GPT, LangGraph) compose into Agentic RAG workflows [@singh2025]. The Weight-Bleeding engine acts as the controlled semantic retrieval layer within this architecture, where the agent handles query decomposition, adaptive iteration, and result synthesis. This decoupling of retrieval (local, CPU-bound, semantically controlled) from reasoning (LLM-driven) aligns with the emerging multi-layer MCP architectures in agentic systems [@queenbee2026; @hybridagentic2026], where the MCP tool layer provides governed, auditable access to domain-specific knowledge [@bolla2025].

The scoring pipeline processes each paper through:

1. Temporal filtering (year ≥ start_year)
2. Anchor matching (exact category keywords with context disambiguation)
3. Hybrid relevance scoring — Weight-Bleeding centroid similarity as base with keyword regex as a configurable bonus term
4. PRISMA-compliant export

# Related Work

**Echo embeddings** [@echo2024] (ICLR 2025) apply term repetition to decoder-only LLMs to overcome causal attention limitations, repeating the entire input text twice and extracting from the second occurrence. Our work differs in several key aspects: (1) we target bi-encoders (all-MiniLM-L6-v2 [@minilm2024], 22M parameters) rather than decoder-only LLMs (Mistral-7B, 7B parameters); (2) the weighted centroid is computed via embedding-space interpolation — a term with weight $W$ contributes $W$ times its embedding vector to the reference centroid, without modifying the model, repeating the input, or incurring token-length penalties; (3) Weight-Bleeding runs on CPU whereas Echo requires GPU; (4) our repetition is selective (only high-weight terms) rather than full-text.

**ASReview** [@asreview2020] is the leading open-source SLR tool, using active learning to prioritize screening. It requires labeled data to train classifiers. Our tool operates zero-shot — the researcher defines domain weights in a configuration file, and both keyword and semantic scoring adapt without any labeled examples.

**SGPT** [@sgpt2022] proposed weighted mean pooling for decoder-only LLMs using position-based weights. **SIF embeddings** [@sif2017] weight terms by corpus frequency. Both modify the pooling strategy itself. Weight-Bleeding achieves weighting without modifying the model architecture — the centroid is computed directly in embedding space via a weighted sum of the base and term vectors.

Two recent works address embedding generation from decoder-only LLMs: **LLM2Vec** [@llm2vec2024] uses bidirectional attention masking and next-token-prediction fine-tuning to convert any decoder into an encoder, while **GRIT** [@grit2024] (ICLR 2025) trains a single model for both generative and representational tasks. Both require additional training — Weight-Bleeding is zero-shot and requires no fine-tuning.

**MCP and Agentic RAG.** The Model Context Protocol [@mcp2024] has rapidly become the standard interface for connecting LLMs to external tools and databases, adopted across major AI platforms following its donation to the Linux Foundation in 2025. The SoK on Agentic RAG [@mishra2026] formalizes these systems as partially observable Markov decision processes, identifying retrieval misalignment — when the retrieval layer cannot reflect task-specific priorities — as a critical systemic risk. Queen-Bee Agents [@queenbee2026] propose a governed multi-agent architecture where a Queen control plane retrieves capabilities and compiles structured BeeSpec execution plans that specialized Bee agents execute through constrained MCP connectors. The Agentic Hybrid Retrieval architecture [@hybridagentic2026] combines BM25 lexical search with dense embeddings orchestrated by an LLM agent that iteratively plans queries and evaluates results. In financial decision making, multi-agent frameworks with MCP integration [@financialmcp2025] deploy specialized agents (data retrieval, analysis, risk evaluation) coordinated through standardized tool interfaces. These works validate the broader pattern of tool-based retrieval systems, but none target systematic literature review — the domain Academic Hunter addresses through its Weight-Bleeding scoring engine and multi-source SLR pipeline, directly mitigating the retrieval misalignment risk identified by Mishra et al.

# Key Features

- **Weight-Bleeding scoring**: embedding-space centroid interpolation with configurable per-term weights; keyword regex applied as a bonus term rather than the scoring foundation.
- **Multi-source aggregation**: concurrent queries across 16 academic APIs and preprint servers with domain-level rate limiting and exponential backoff.
- **PRISMA compliance**: automatic PRISMA flow report with Mermaid diagrams.
- **MCP server**: 35+ tools, 4 resources, 2 prompts for AI-assisted research. Includes health check (`server_status`), SSE remote access, and full error handling via typed exceptions (`MCPToolError` hierarchy).
- **MiniLM-powered analysis**: the same all-MiniLM-L6-v2 embedding model that powers Weight-Bleeding also drives topic clustering (BERTopic), novelty/outlier detection (EllipticEnvelope), semantic deduplication (cosine similarity), research landscape visualization (UMAP 2D), extractive summarization (centroid + MMR), and cross-encoder re-ranking.
- **Agentic RAG ready**: MCP tools enable external LLM agents to orchestrate multi-step literature review workflows, combining iterative retrieval with autonomous query refinement and synthesis.
- **Fully local**: no GPU required, no API keys for core functionality, ChromaDB with ONNX embeddings [@onnx2024] runs on CPU.

# Quick Start

Install Academic Hunter from source:

```bash
pip install git+https://github.com/devfelipenunes/academic-hunter.git
```

Or run with Docker:

```bash
docker run -p 8000:8000 devfelipenunes/academic-hunter
```

Configure a search by editing `config.json`:

```json
{
  "topic": "CBDC and atomic settlement",
  "anchors": {
    "Settlement": ["atomic settlement", "finality"],
    "CBDC": ["central bank digital currency"]
  },
  "technical_weights": { "atomic settlement": 5.0, "finality": 3.0 },
  "settings": { "start_year": 2020, "limit_per_query": 100 }
}
```

Run a full SLR pipeline:

```bash
academic-hunter run        # search 7 APIs, score, deduplicate, export
academic-mcp               # start MCP server (stdio) for LLM agent integration
```

The MCP server exposes 35+ tools, 4 resources, and 2 prompts. Connect any MCP-compatible client (Claude Desktop, LangChain, any custom agent):

```bash
# Example: Claude Desktop config (local stdio)
# ~/.claude/claude_desktop_config.json
{
  "mcpServers": {
    "academic-hunter": {
      "command": "academic-mcp"
    }
  }
}
```

For remote access, start the server in SSE mode:

```bash
academic-mcp -t sse --host 0.0.0.0 --port 8080
```

Health check endpoint (SSE mode): `GET http://host:port/health`

The server also supports environment variable configuration:

- `ACADEMIC_MCP_TRANSPORT` (stdio or sse)
- `ACADEMIC_MCP_HOST` (bind address)
- `ACADEMIC_MCP_PORT` (port number)

Full documentation is available at [https://devfelipenunes.github.io/academic-hunter](https://devfelipenunes.github.io/academic-hunter) and the source code repository includes a comprehensive test suite with 155 tests covering all scoring modes, output transforms, MCP tool endpoints, connector APIs, and integration tests.

# Experiments

We validate Academic Hunter's scoring pipeline through a three-mode ablation study across seven academic databases. The full experimental protocol, baseline comparisons against SGPT (positional), SIF (frequency), and Echo (repetition) strategies — all shown to have limited or no effect on mean-pooling bi-encoders — are detailed in the companion method paper, together with cross-encoder correlation studies and model robustness analysis across three embedding architectures. Key results are summarized below.

**Ecosystem validation.** The MCP server has been tested end-to-end with a complete systematic literature review workflow spanning 16 tools in sequence: topic discovery → configuration → semantic search → trend analysis → novelty detection → related-paper recommendation → topic clustering → temporal evolution → semantic deduplication → extractive summarization → research landscape visualization → citation analysis → open-access lookup → multi-format export. This validates the architecture as a production-ready agentic research platform.

**Ablation.** Three scoring modes (keyword-only, Weight-Bleeding embedding-only, hybrid) were evaluated on the same configuration across 2,300+ papers from ArXiv, Crossref, OpenAlex, Semantic Scholar, CORE, DBLP, and DOAJ. All modes converge to near-identical final sets — the $\sqrt{\sigma}$ output scaling achieves 92.7% overlap across modes, up from 47.8% under linear scaling. Weight-Bleeding adds semantically similar papers that exact matching misses (3 unique papers) while keyword-only captures exact-match phrases the bi-encoder overlooks (4 unique papers).

**Baseline.** Against a vanilla bi-encoder on 500 indexed papers, Weight-Bleeding produces differentiated rankings (Spearman $\rho = 0.968$, top-10 overlap 60%). Cross-domain validation confirms the effect is domain-specific, not a global bias: SLR and blockchain configurations produce negatively correlated rankings ($\rho = -0.75$). At threshold 5.0, Weight-Bleeding passes 151 papers vs 92 for the vanilla baseline ($+$59 papers).

**Efficiency.** All scoring runs on a single CPU core. The centroid is computed once ($\sim$525 ms) and per-paper scoring is a single cosine similarity ($\sim$0.01 ms). Weight-Bleeding is $\sim$7.5$\times$ faster than cross-encoder reranking, with the gap growing linearly with corpus size.

# Availability

Academic Hunter is open-source under the MIT license at:
[https://github.com/devfelipenunes/academic-hunter](https://github.com/devfelipenunes/academic-hunter)

The version described in this paper is archived on Zenodo (DOI pending). The companion method paper provides a detailed analysis of the Weight-Bleeding algorithm, covering baseline comparisons, Echo repetition benchmarks across three embedding models (MiniLM, BGE-base, GTE-small), cross-encoder validation, weight sensitivity, model robustness, and ablation studies across six output transformations.

Documentation, tutorials, and API reference are available at the project website:
[https://devfelipenunes.github.io/academic-hunter](https://devfelipenunes.github.io/academic-hunter)

The repository includes a test suite (21 regression tests), issue templates for bug reports and feature requests, and automated CI/CD via GitHub Actions.

# Conclusion

We presented Academic Hunter, an open-source SLR tool that bridges traditional systematic review methodology with modern Agentic RAG infrastructure. Its Weight-Bleeding engine provides configurable embedding-space relevance scoring — a novel approach that biases bi-encoder embeddings toward domain-specific terms without modifying the model, requiring GPU compute, or needing labeled data. The tool's MCP server exposes 35+ retrieval and analysis tools, 4 resources, and 2 prompts that external LLM agents can orchestrate autonomously, positioning Academic Hunter as both a standalone SLR pipeline and the retrieval backbone for agentic research workflows. The same MiniLM embedding model that powers Weight-Bleeding also drives topic clustering, novelty detection, semantic deduplication, extractive summarization, and research landscape visualization — maximizing the value of a single 22MB model across 12 distinct analytical capabilities.

Our experiments confirm the scoring pipeline is robust (92.7% cross-mode overlap), computationally efficient ($\sim$7.5$\times$ faster than cross-encoder reranking), and domain-adaptable (negatively correlated SLR and blockchain rankings, $\rho = -0.75$). The companion method paper provides detailed experimental analysis including baseline comparisons, Echo repetition benchmarks, cross-encoder validation, threshold sensitivity, multi-model robustness, and ablation studies across six output transformations.

**Limitations:** (1) Cross-encoder correlation is inherently low, as Weight-Bleeding targets semantic similarity rather than conversational relevance, though we argue this is appropriate for SLR tasks; (2) Semantic Scholar and DBLP are rate-limited without API keys; (3) Term influence on the centroid scales linearly with $W$, providing predictable control but lacking threshold effects — partially mitigated by the output-level $\sqrt{\sigma}$ transform.

# Acknowledgements

We thank the open-source maintainers of ChromaDB [@chromadb2024], sentence-transformers [@sentence-transformers], and FastMCP [@fastmcp2025] for their foundational work.

# References
