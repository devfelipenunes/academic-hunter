# Academic Hunter V2 Implementation Plan

**Goal:** Transform `academic_hunter.py` into a high-coverage, systematic literature review engine focused 100% on academic papers.

**Architecture:** A modular class-based approach with dedicated API connectors, a centralized scoring engine driven by `config.json`, and a DOI-based deduplication layer.

**Tech Stack:** Python 3.12, Requests, Pandas, XML/ETree.

---

### Task 1: Update Configuration Structure

**Files:**
- Modify: `config.json`

- **Step 1:** Add `settings` and `pesos_tecnicos` sections to `config.json`.
- **Step 2:** Ensure all technical strings have corresponding weights in `pesos_tecnicos`.

---

### Task 2: Refactor Initialization and Config Loading

**Files:**
- Modify: `src/academic_hunter.py`

- **Step 1:** Update `__init__` and `load_config` methods to use the new `config.json` structure (settings, anchors, tech_strings, tech_weights).
- **Step 2:** Pre-compile regex patterns for technical weights during initialization for performance.
- **Step 3:** Remove the redundant `setup_weights` method.

---

### Task 3: Revamp Scoring Logic (Title Bonus & Weights)

**Files:**
- Modify: `src/academic_hunter.py`

- **Step 1:** Update `calculate_score` to use `self.compiled_patterns` and implement a multiplier for terms found in the title (configurable via `title_multiplier` in settings).
- **Step 2:** Use regex with word boundaries to prevent substring matching errors (e.g., preventing "tps" from matching "https").
- **Step 3:** Ensure the scoring logic prevents double counting the base weight if a term is already found in the title.

---

### Task 4: Implement OpenAlex Connector

**Files:**
- Modify: `src/academic_hunter.py`

- **Step 1:** Add the `fetch_openalex` method and register the `https://api.openalex.org/works` endpoint.
- **Step 2:** Implement logic to decode the "inverted index" abstract format returned by OpenAlex so it can be used for scoring.
- **Step 3:** Ensure proper URL and DOI normalization.

---

### Task 5: Enhance Data Sources and Integration

**Files:**
- Modify: `src/academic_hunter.py`

- **Step 1:** Fix the Semantic Scholar search query to include all anchor and technical terms, rather than just the first items in the lists.
- **Step 2:** Re-integrate the `fetch_core_ac` method into the main `run()` pipeline to maximize Open Access coverage.

---

### Task 6: Implement DOI-based Deduplication & Rate Limiting

**Files:**
- Modify: `src/academic_hunter.py`

- **Step 1:** Update the `run` method to use DOIs for deduplication. If a DOI is missing, use a lowercase title slug.
- **Step 2:** Merge results from different sources, retaining the one with the highest citation count.
- **Step 3:** Implement API rate limiting by adding `time.sleep(2)` at the end of the inner processing loop.

---

### Task 7: Master Report Export (Markdown)

**Files:**
- Modify: `src/academic_hunter.py`

- **Step 1:** Update `export_results` to generate a Markdown Master Report (`RELATORIO_ELITE_<timestamp>.md`) containing the top 50 papers sorted by score.
- **Step 2:** Ensure both the CSV dataset and the Markdown report are properly saved in the `results/` directory.
