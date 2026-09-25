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
git clone https://github.com/devfelipenunes/academic-hunter.git
cd academic-hunter

# Set up virtual environment
python3 -m venv venv
source venv/bin/activate

# Install the package with its development extras — the same set `make
# install-dev` installs, and the same extras `install.py`, the Dockerfile and
# the CI workflows use:
pip install -e ".[ml,fulltext,dev]"
```

This is the contributor path. Users install the published package with `uvx`
instead — no clone, no virtualenv, and no absolute path in their client config —
which is what `docs/mcp_setup.md` documents first. Changes to the config or data
search order have to work in both, and `tests/core/test_paths.py` is where that
is pinned: the `installed` fixture stands in for the case where no
`pyproject.toml` sits above the package.

### 2. Running Tests

Before submitting any changes, verify that the entire test suite passes:

```bash
make test
```

Tests that reach real APIs are marked `integration` and deselected by default;
`make test-all` runs those too.

---

## 🏗️ Core Architecture Overview

The package follows an inverted-dependency (hexagonal) layout under
`src/academic_hunter/`, enforced mechanically by `tests/test_architecture.py` —
an import in the wrong direction fails the suite. `docs/architecture.md` has the
long version.

1. **`core/`** — the domain. Imports nothing from the layers below it.
   - **`models/paper.py`**: the `Paper` domain model — slug generation, metadata
     merging, peer-review heuristic detection, metadata validation.
   - **`nlp/scorer.py`**: the scoring system (`AcademicScorer`) — technical
     density, title bonuses, contextual checks.
   - **`infra/cache.py`**: thread-safe persistent request cache on SQLite.
   - **`ports/`**: the contracts the adapters implement (`BaseExporter`,
     `BaseScreener`, `BaseVectorStore`, `ConnectorPort`).
2. **`app/`** — the application layer. **`main.py`** holds `AcademicHunter`, the
   central execution orchestrator and the only module that imports plugins: it
   runs the multi-threaded pipeline, coordinates rate-limiting pacing delays,
   aggregates results and invokes filters.
3. **`plugins/`** — the adapters:
   - **`connectors/`**: isolated academic database clients (e.g. ArXiv, OpenAlex, Semantic Scholar). Every client inherits from `BaseConnector`.
   - **`exporters/`**: Specialized document generators (CSV, RIS, BibTeX, PRISMA flow, and Markdown reports). Every format client inherits from `BaseExporter`.
4. **`interfaces/`** — the MCP server and its tools. It is the only public
   surface; the interactive CLI was removed.

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

There is no dictionary to edit by hand: every module in `connectors/` is
imported and scanned for `BaseConnector` subclasses at startup. What you do add
is the module's stem to `_CONNECTOR_NAMES` in
[`src/academic_hunter/plugins/connectors/__init__.py`](src/academic_hunter/plugins/connectors/__init__.py),
which is what keeps the display keys stable:

```python
_CONNECTOR_NAMES = {
    ...
    "pubmed": "PubMed",
}
```

The class must declare a matching `SOURCE_NAME = "PubMed"`. Registration refuses
a connector that stamps a different name than the one it is filed under —
otherwise a run reports the same source twice, once with a count and once with a
zero.

### 3. Expose Proxy Method (Optional)

Add a facade proxy fetch method on `AcademicHunter` inside [src/academic_hunter/app/facades.py](src/academic_hunter/app/facades.py) to enable direct queries:

```python
    def fetch_pubmed(self, anchors: List[str], tech_strings: List[str], limit: int = 50) -> List[Dict[str, Any]]:
        return self.connectors["PubMed"].fetch(anchors, tech_strings, limit)
```

### 4. Write Unit Tests

Add a new mock-based test suite (e.g., `tests/test_pubmed_mock.py`) to verify the correctness of the parser and integration with the database responses. Note that the suite runs offline by default — the tests that reach real APIs carry the `integration` marker and are deselected. Make sure everything passes:

```bash
make test
```
