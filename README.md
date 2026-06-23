# Academic Hunter V2 🎯

**Academic Hunter** is a professional OSINT (Open Source Intelligence) tool designed for systematic literature reviews in the fields of **Fintech, Payments, and Financial Infrastructure**. 

It automates the mining of high-impact scholarly articles across multiple global databases, ranking them using a sophisticated "Technical Elite Score" to separate foundational research from the noise.

## 🚀 Key Features

*   **Multi-Source Aggregation:** Simultaneous querying of **OpenAlex**, **Crossref**, **ArXiv**, **Semantic Scholar**, and **CORE.ac.uk**.
*   **Elite Scoring Engine:** Dynamic relevance ranking based on technical density, with a **1.5x multiplier** for terms found in titles.
*   **DOI-Based Deduplication:** Intelligent merging of results from different sources using Digital Object Identifiers to ensure a clean dataset.
*   **High-Coverage Search:** Grid-search logic that combines industry "anchors" (e.g., Pix, FedNow, CBDC) with technical strings (e.g., ISO 20022, ZKP, Atomic Settlement).
*   **Professional Reporting:** Generates both a raw **CSV dataset** for data analysis and a formatted **Markdown Master Report** for immediate reading.
*   **OpenAlex Decoder:** Built-in logic to reconstruct abstracts from OpenAlex's inverted index format.

## 🛠️ Tech Stack

*   **Language:** Python 3.12+
*   **Libraries:** Pandas, Requests, XML/ETree
*   **Architecture:** Modular Class-based API Connectors

## ⚙️ Configuration

The tool is entirely driven by `config.json`. You can customize:

*   **Anchors:** The market/project terms you are looking for.
*   **Technical Strings:** The specific technologies or protocols you want to cross-reference.
*   **Technical Weights:** Fine-grained control over the scoring algorithm.
*   **Settings:** Date filters, result limits, and scoring precision.

Example `config.json` snippet:
```json
"pesos_tecnicos": {
    "atomic settlement": 5.0,
    "iso 20022": 5.0,
    "interoperability": 3.0,
    "scalability": 1.5
}
```

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

## 🏃 Usage

1. Copy the configuration template and fill in your search parameters:
   ```bash
   cp config.example.json config.json
   ```

2. (Optional) Set your API keys in your environment:
   ```bash
   export SEMANTIC_SCHOLAR_API_KEY="your-s2-key"
   export CORE_API_KEY="your-core-key"
   export OPENALEX_API_KEY="your-openalex-key"
   ```

3. Run the main script:
   ```bash
   python main.py
   ```

The tool will iterate through your configuration and save the results in the `results/` directory:
*   `academic_dataset_TIMESTAMP.csv`: Full list of validated papers.
*   `RELATORIO_ELITE_TIMESTAMP.md`: Top 50 papers formatted for reading.

## 📊 Evaluation

The tool is optimized for high-fidelity research. In our audits, the V2 engine successfully identified state-of-the-art papers (2025/2026) regarding **mBridge, JIT Liquidity, and Quantum-Resistant CBDCs** that are often missed by standard keyword searches.

---
*Developed for advanced academic and industrial research in financial technologies.*
