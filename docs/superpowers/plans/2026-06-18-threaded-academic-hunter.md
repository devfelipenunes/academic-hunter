# Multi-Threaded Academic Hunter Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the mining pipeline to run API sources in parallel using multi-threading.

**Architecture:** Implement a worker pattern where each API source runs in its own thread. Each thread iterates through all search combinations. A global lock ensures thread-safe updates to shared state.

**Tech Stack:** Python 3.12, `threading` library, `requests`, `pandas`.

---

### Task 1: Implement the API Worker Method

**Files:**
- Modify: `src/academic_hunter.py`

- [ ] **Step 1: Implement `_api_worker` method**
  - Create a private method `_api_worker(self, source_name, fetch_func, limit_per_source)`.
  - It must iterate through `self.anchors` and `self.tech_strings`.
  - For each combination, call `fetch_func(anchor_list, tech_list, limit=limit_per_source)`.
  - Process results with `self._process_paper`.
  - Add a 10s sleep for "CORE" source after each search combination.

```python
    def _api_worker(self, source_name: str, fetch_func, limit_per_source: int):
        """Worker thread function for a specific API source."""
        for anchor_cat, anchor_list in self.anchors.items():
            for tech_cat, tech_list in self.tech_strings.items():
                # print(f"   [{source_name}] Mining: {anchor_cat} x {tech_cat}")
                try:
                    results = fetch_func(anchor_list, tech_list, limit=limit_per_source)
                    for paper in results:
                        self._process_paper(paper, anchor_cat, tech_cat, anchor_list, tech_list)
                except Exception as e:
                    print(f"   [{source_name} Worker Error] {e}")
                
                if source_name == "CORE":
                    time.sleep(10) # Respect CORE's strict rate limit
```

- [ ] **Step 2: Commit worker implementation**

```bash
git add src/academic_hunter.py
git commit -m "feat: implement _api_worker for multi-threaded mining"
```

---

### Task 2: Refactor the `run` Method for Orchestration

**Files:**
- Modify: `src/academic_hunter.py`

- [ ] **Step 1: Update `run` method to use threads**
  - Reset state under lock.
  - Define workers as tuples of `(name, fetch_func)`.
  - Create, start, and join threads.
  - Export results at the end.

```python
    def run(self, limit_per_source: int = 100):
        print(f"🚀 Initializing Multi-Threaded Academic Hunter V2 Pipeline...")
        start_time = time.time()
        
        with self.lock:
            self.consolidated_results = {} 
            self.seen_ids = set() 
            self.stats = {
                "identified": {},
                "duplicates_removed": 0,
                "excluded_score": 0,
                "included_final": 0
            }

        workers = [
            ("ArXiv", self.fetch_arxiv),
            ("Crossref", self.fetch_crossref),
            ("Semantic Scholar", self.fetch_semantic_scholar),
            ("OpenAlex", self.fetch_openalex),
            ("CORE", self.fetch_core_ac)
        ]

        threads = []
        for name, func in workers:
            t = threading.Thread(target=self._api_worker, args=(name, func, limit_per_source))
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        elapsed = time.time() - start_time
        print(f"\n⏱️  Mining completed in {elapsed:.2f} seconds.")
        
        with self.lock:
            results_list = list(self.consolidated_results.values())
        self.export_results(results_list)
```

- [ ] **Step 2: Commit orchestration refactor**

```bash
git add src/academic_hunter.py
git commit -m "feat: refactor run() to use multi-threaded orchestration"
```

---

### Task 3: Verification and Stress Test

**Files:**
- Create: `tests/test_threaded_engine.py`

- [ ] **Step 1: Create a test for threading resilience**
  - Use a mock configuration.
  - Verify that `PRISMA STATS` are correctly accumulated across threads.
  - Ensure `consolidated_results` contains papers from multiple sources.

```python
import pytest
from src.academic_hunter import AcademicHunter
import json
from pathlib import Path

def test_threaded_execution_integrity(tmp_path):
    config = {
        "settings": {"min_relevance_score": 0, "start_year": 2024},
        "ancoras": {"test": ["artificial intelligence"]},
        "strings_tecnicas": {"test": ["machine learning"]},
        "pesos_tecnicos": {"ai": 1.0}
    }
    config_path = tmp_path / "config.json"
    with open(config_path, 'w') as f:
        json.dump(config, f)
        
    hunter = AcademicHunter(config_path=str(config_path), output_dir=str(tmp_path))
    
    # Run with small limit to speed up test
    hunter.run(limit_per_source=5)
    
    assert hunter.stats["included_final"] > 0
    assert len(hunter.consolidated_results) > 0
    assert sum(hunter.stats["identified"].values()) >= hunter.stats["included_final"]
```

- [ ] **Step 2: Run verification test**

Run: `pytest tests/test_threaded_engine.py -v`
Expected: PASS

- [ ] **Step 3: Commit verification**

```bash
git add tests/test_threaded_engine.py
git commit -m "test: add threading integrity verification"
```
