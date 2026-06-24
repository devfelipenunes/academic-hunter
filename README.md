# Academic Hunter V2 🎯
![Academic Hunter](https://img.shields.io/badge/Status-Active-success) ![Python](https://img.shields.io/badge/Python-3.12+-blue) ![MCP](https://img.shields.io/badge/Protocol-MCP_Ready-orange)

**Academic Hunter** is a professional OSINT (Open Source Intelligence) tool and **Multi-Agent MCP Server** designed for Decentralized Science (DeSci) and systematic literature reviews.

It automates the mining of high-impact scholarly articles across multiple global databases, ranking them using a sophisticated "Technical Elite Score", and exposes these capabilities to LLMs via the **Model Context Protocol (MCP)**.

---

## 🌟 Dual-Track Architecture

Academic Hunter is built with a **Hexagonal Architecture**. It can be used in two ways:

### 1. The Core Engine (For Data Engineers & Researchers)
Use the raw Python Engine to run massive, concurrent scrapes across multiple APIs.
*   **Multi-Source Aggregation:** OpenAlex, Crossref, ArXiv, Semantic Scholar, CORE.ac.uk.
*   **Elite Scoring Engine:** Dynamic relevance ranking with dynamic multipliers.
*   **DOI-Based Deduplication:** Intelligent merging of results using DOIs.
*   **Professional Reporting:** Generates CSV datasets and Markdown Master Reports.

### 2. The Multi-Agent MCP Server (For AI Engineers & LLMs)
Connect Academic Hunter directly to **Claude Desktop**, **Cursor**, or any MCP client.
By turning the Core Engine into an MCP Server, AI Agents can now:
*    autonomously perform **Quick Topic Discovery** via API.
*    autonomously **Update Configuration** with optimal technical strings.
*    autonomously **Execute Snowballing** (explore citation graphs).
*    autonomously **Export to Obsidian** to build your Second Brain.

(See the `docs/superpowers/agents/` directory for our Role-Playing Agent Prompts).

---

## 📥 Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/youruser/academic-hunter.git
   cd academic-hunter
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/macOS
   # or
   .\venv\Scripts\activate   # Windows
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

---

## 🏃 Usage Track A: Python CLI

1. Copy the configuration template and fill in your search parameters:
   ```bash
   cp config.example.json config.json
   ```

2. Run the main script:
   ```bash
   python main.py
   ```

The tool will save results in the `results/` directory (`.csv` and `.md`).

---

## 🤖 Usage Track B: MCP Server

To use Academic Hunter as an AI Tool inside Claude Desktop or Cursor IDE, add the following to your MCP configuration file (`mcp.json` or `claude_desktop_config.json`):

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

Restart your client. Your LLM now has full control over the DeSci OSINT engine!

---

## 📚 Documentation
- **[Architecture](ARCHITECTURE.md)**: Deep dive into the Hexagonal design.
- **[Core Engine](docs/core_engine.md)**: Detailed breakdown of the Python internals (`pipeline`, `nlp`, `engine`).
- **[Contributing](CONTRIBUTING.md)**: Guidelines for PRs and issues.

---
*Developed for advanced academic and industrial research in financial technologies and beyond.*
