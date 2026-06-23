# Contributing to Academic Hunter

Thank you for your interest in contributing to **Academic Hunter**! We want to make it as easy and transparent as possible for you to contribute to this project, whether it's through:

- Reporting a bug
- Discussing the current state of the code
- Submitting a fix
- Proposing or implementing new academic database connectors

---

## 🛠️ Getting Started

### 1. Development Setup

Clone the repository and initialize the virtual environment:

```bash
# Clone the repository
git clone https://github.com/fnunes/pesquisa_academica.git
cd pesquisa_academica

# Set up virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install pytest pandas requests
```

### 2. Running Tests

Before submitting any changes, verify that the entire test suite passes:

```bash
PYTHONPATH=. venv/bin/pytest
```

---

## 🏗️ Core Architecture Overview

The package is split into separate modular components under `src/academic_hunter/`:

1. **`core/`**:
   - **`engine.py`**: The central execution orchestrator (`AcademicHunter`). Handles the multi-threaded pipeline, coordinates rate-limiting pacing delays, aggregates results, and invokes filters.
   - **`models.py`**: Contains the `Paper` domain model class, wrapping slug generation, metadata merging, peer-review heuristic detection, and metadata validation.
   - **`scorer.py`**: The scoring system (`AcademicScorer`) evaluating technical density, title bonuses, and contextual checks.
   - **`cache.py`**: Thread-safe persistent request cache wrapper using SQLite.
2. **`plugins/`**:
   - **`connectors/`**: Isolated academic database clients (e.g. ArXiv, OpenAlex, Semantic Scholar). Every client inherits from `BaseConnector`.
   - **`exporters/`**: Specialized document generators (CSV, RIS, BibTeX, PRISMA flow, and Markdown reports). Every format client inherits from `BaseExporter`.

---

## 🔌 Adding a New Database Connector

Adding support for a new academic source (e.g., PubMed, Scopus) is straightforward under our modular plugin architecture:

### 1. Create a Connector Module

Create a new file in `src/academic_hunter/plugins/connectors/` (e.g., `pubmed.py`) and implement a class subclassing `BaseConnector`:

```python
from typing import List, Dict, Any
from .base import BaseConnector

class PubmedConnector(BaseConnector):
    def fetch(self, anchors: List[str], tech_strings: List[str], limit: int = 50) -> List[Dict[str, Any]]:
        # 1. Compose search query format
        query = f"..."
        
        with self.lock:
            self.query_history.append({"Source": "PubMed", "Query": query})
            
        results = []
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {"term": query, "retmode": "json"}
        
        # 2. Fetch using self._make_request() to respect caching, headers, and pacing
        data = self._make_request(url, params=params)
        if data:
            for item in data.get("esearchresult", {}).get("idlist", []):
                results.append({
                    "Title": item.get("title"),
                    "Abstract": item.get("abstract", ""),
                    "Year": item.get("year"),
                    "URL": f"https://pubmed.ncbi.nlm.nih.gov/{item.get('id')}",
                    "Source": "PubMed",
                    "Citations": 0,
                    "DOI": item.get("doi", ""),
                    "Peer_Reviewed": "Yes",
                    "Venue": item.get("journal", "PubMed Journal")
                })
        return results[:limit]
```

### 2. Register the Connector

In [src/academic_hunter/plugins/connectors/__init__.py](file:///l/disk0/fnunes/Documentos/me/pesquisa_academica/src/academic_hunter/plugins/connectors/__init__.py), import your class and register it inside the `CONNECTORS` dictionary:

```python
from .pubmed import PubmedConnector

CONNECTORS = {
    ...
    "PubMed": PubmedConnector
}
```

### 3. Expose Proxy Method (Optional)

Add a facade proxy fetch method on `AcademicHunter` inside [src/academic_hunter/core/engine.py](file:///l/disk0/fnunes/Documentos/me/pesquisa_academica/src/academic_hunter/core/engine.py) to enable direct queries:

```python
    def fetch_pubmed(self, anchors: List[str], tech_strings: List[str], limit: int = 50) -> List[Dict[str, Any]]:
        return self.connectors["PubMed"].fetch(anchors, tech_strings, limit)
```

### 4. Write Unit Tests

Add a new mock-based test suite (e.g., `tests/test_pubmed_mock.py`) to verify the correctness of the parser and integration with the database responses. Make sure all tests pass:
```bash
PYTHONPATH=. ./venv/bin/pytest
```
