<div align="center">
  <h1>🎯 Academic Hunter V2</h1>
  <p><b>Automated Systematic Literature Reviews for Decentralized Science (DeSci)</b></p>

  [![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
  [![MCP Ready](https://img.shields.io/badge/Protocol-MCP_Ready-orange.svg)](https://modelcontextprotocol.io/)
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

1. **Clone & Install:**
   ```bash
   git clone https://github.com/devfelipenunes/academic-hunter.git
   cd academic-hunter
   python install.py
   ```
   *(The automated installer will set up your environment and optionally inject the MCP server into Claude Desktop for you).*

2. **Configure your Research Anchors:**
   *(Edit the generated `config.json` with your specific market keywords and technical weights).*

3. **Hunt (Command-Line Interface):**
   To run the main engine and sweep all academic databases simultaneously, activate the virtual environment created during installation and execute the command:
   
   ```bash
   source venv/bin/activate  # (No Windows: venv\Scripts\activate)
   academic-hunter
   ```
   
   *Note: By default, running `academic-hunter` will use the global limit defined in your `config.json` (`limit_per_query` field). If you want to limit or expand the results for a quick test, you can force a value with the flag:*
   ```bash
   academic-hunter --limit 5
   ```
   *Results will be generated in the `results/` directory as rich CSV datasets, Prisma flows, and Markdown reports.*

---

## ⚙️ The Brain: `config.json`

The `config.json` file is the heart of Academic Hunter. Unlike common scrapers that just pull everything they find, Hunter uses this file to act as an experienced researcher, filtering noise and mathematically scoring the relevance of each article. 

It improves results by focusing on four main pillars:

1. **`settings`**: Defines research limits, minimum cut-off score (`min_relevance_score`), start year (`start_year`), and your **API keys**. Placing API keys here (like Semantic Scholar) prevents *Rate Limit* errors, speeds up extraction, and opens doors to deeper metadata.
2. **`anchors`**: Your primary research categories (e.g., "Digital Wallets", "Interbank Settlement"). The engine will only analyze papers that intersect with these core industry themes, immediately eliminating academic research with no market application.
3. **`technical_strings`**: Deep technical terms (e.g., "zero-knowledge proof", "ISO 20022"). The algorithm reads the Title and Abstract of each article looking for these terms to verify the degree of technological sophistication of that paper.
4. **`technical_weights`**: The secret of the NLP algorithm. You assign numerical "weights" (e.g., 5.0, 3.0) to each technical term. If the engine finds the terms in the paper, it adds the points (giving extra multipliers if it is in the title). Only papers that pass the `min_relevance_score` survive and enter your Master Report!

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
