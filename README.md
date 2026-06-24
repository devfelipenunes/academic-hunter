<div align="center">
  <h1>🎯 Academic Hunter V2</h1>
  <p><b>Automated Systematic Literature Reviews for Decentralized Science (DeSci)</b></p>

  [![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
  [![MCP Ready](https://img.shields.io/badge/Protocol-MCP_Ready-orange.svg)](https://modelcontextprotocol.io/)
  <a href="https://smithery.ai/server/academic-hunter"><img alt="Smithery Badge" src="https://smithery.ai/badge/academic-hunter"></a>
</div>

<br/>

Academic Hunter is a professional Open Source Intelligence (OSINT) engine that automates the mining, deduplication, and mathematical relevance scoring of high-impact scholarly articles. 

Built with a **Hexagonal Architecture**, it serves two masters: it can be run as a raw Python CLI for Data Engineers, or plugged directly into your favorite Large Language Model (like Claude or Cursor) as an autonomous **Model Context Protocol (MCP)** server.

---

## ✨ Features

- 🧠 **Elite Scoring Engine:** NLP and Keyword evaluators that score papers mathematically based on your research anchors.
- 🔗 **Multi-Source Aggregation:** Concurrently scrapes Semantic Scholar, OpenAlex, Crossref, ArXiv, and CORE.ac.uk.
- 🛡️ **Intelligent Deduplication:** Uses Strict-DOI and Fuzzy Title matching to eliminate academic noise.
- 🤖 **Native MCP Server:** Let Claude autonomously explore citation graphs, configure search parameters, and export to your Obsidian Second Brain.
- 🔌 **Plugin Architecture:** Easily hot-swap Vector Stores (Native RAG) and NLP Screeners.

---

## 🚀 Quickstart

### Track A: Use via Claude Desktop (Zero-Code)

The easiest way to use Academic Hunter is to install it as a tool for your AI assistant via Smithery:

```bash
npx -y @smithery/cli install academic-hunter --client claude
```

*(You can now ask Claude: "Run a full systematic review on Zero-Knowledge Proofs in CBDCs" and watch the magic happen).*

### Track B: Use as a Python CLI (Data Engineers)

1. **Clone & Install:**
   ```bash
   git clone https://github.com/devfelipenunes/academic-hunter.git
   cd academic-hunter
   pip install -e .
   ```

2. **Configure your Research Anchors:**
   ```bash
   cp config.example.json config.json
   ```
   *(Edit `config.json` with your specific market keywords and technical weights).*

3. **Hunt:**
   ```bash
   academic-hunter
   ```
   *Results will be generated in the `results/` directory as rich CSV datasets and Markdown reports.*

---

## 🏛️ Architecture & Documentation

Academic Hunter is designed for massive scalability without Spaghetti Code. Dive into our internal documentation to build your own plugins:

- 🗺️ **[Hexagonal Architecture Map](docs/architecture.md)**
- ⚙️ **[The Core Engine](docs/core_engine.md)**
- 🧩 **[How to Build NLP Screener Plugins](docs/plugins/screeners.md)**
- 🗄️ **[How to Build Vector Store Plugins](docs/plugins/vector_stores.md)**
- 🤝 **[Contributing Guidelines](CONTRIBUTING.md)**

---
<div align="center">
  <i>Developed for advanced academic and industrial research. Let the Hunter do the digging.</i>
</div>
