# Academic Hunter Plugin Standards

To ensure Academic Hunter remains a clean, maintainable, and highly scalable Open Source project, all contributors must adhere to the following architecture and naming guidelines when creating new Plugins.

## 1. Naming Conventions (DRY Principle)

We follow the **Don't Repeat Yourself (DRY)** principle for file names.
Do not include the folder name or redundant suffixes in the python file.

- ❌ **Incorrect:** `src/academic_hunter/plugins/screeners/keyword_screener.py`
- ✅ **Correct:** `src/academic_hunter/plugins/screeners/keyword.py`

- ❌ **Incorrect:** `src/academic_hunter/plugins/vector_stores/chroma_store.py`
- ✅ **Correct:** `src/academic_hunter/plugins/vector_stores/chroma.py`

## 2. Interface Contracts (ABCs)

Every plugin module has a `base.py` file containing an **Abstract Base Class (ABC)**.
You **must** inherit from this class and implement its abstract methods. This guarantees that the Core Engine can swap plugins dynamically without breaking.

Example for a new Screener:
```python
from .base import BaseScreener
from typing import Dict, Any

class MyNewScreener(BaseScreener):
    def evaluate(self, paper_data: Dict[str, Any], config: Dict[str, Any]) -> float:
        # Your custom logic here
        return 1.0
```

## 3. Type Hinting and Docstrings

Academic Hunter enforces strict typing (via Pyright) to ensure stability in the DeSci pipelines.
- Every method argument must have a Type Hint (`str`, `Dict[str, Any]`, `List`, etc.).
- Every return value must have a Type Hint (`-> float`, `-> bool`, etc.).
- Every class and method must have a descriptive docstring explaining its purpose.

## 4. Agnosticism

Plugins must never import modules from `core/engine/` or `interfaces/mcp/`. Plugins are isolated adapters. They receive data, process it, and return data. They do not orchestrate the system.
