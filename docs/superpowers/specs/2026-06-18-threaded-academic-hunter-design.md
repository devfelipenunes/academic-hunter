# Design Doc: Multi-Threaded Academic Hunter Orchestration

**Date:** 2026-06-18
**Topic:** Task 3 - Refactoring the mining pipeline for parallel execution.

## 1. Goal
Improve the performance of the `AcademicHunter` pipeline by running API sources in parallel using multi-threading, while respecting rate limits (especially for CORE).

## 2. Architecture

### 2.1. Worker Pattern
Each API source (ArXiv, Crossref, Semantic Scholar, OpenAlex, CORE) will run in its own dedicated thread.

### 2.2. Thread Safety
- `self.lock` (an existing `threading.Lock`) will guard all modifications to shared state:
  - `self.consolidated_results`
  - `self.seen_ids`
  - `self.stats`
- The `_process_paper` method already uses this lock, which ensures that deduplication and scoring are consistent across threads.

### 2.3. Worker Implementation (`_api_worker`)
A new method `_api_worker(source_name, fetch_func, limit_per_source)` will:
1. Iterate through `self.anchors.items()` (category and term list).
2. Iterate through `self.tech_strings.items()` (category and term list).
3. Call `fetch_func(anchor_list, tech_list, limit=limit_per_source)`.
4. Call `self._process_paper` for each returned paper.
5. If `source_name == "CORE"`, sleep for 10 seconds after each request combination.

### 2.4. Orchestration Implementation (`run`)
The `run` method will:
1. Initialize/reset shared state under `self.lock`.
2. Define a list of tuples: `(Source Name, Fetch Method)`.
3. Launch a `threading.Thread` for each tuple calling `_api_worker`.
4. `join()` all threads.
5. Call `self.export_results()` with the consolidated data.

## 3. Data Flow
1. **Orchestrator (`run`)** -> Starts **Workers**
2. **Worker** -> Calls **API Fetcher**
3. **API Fetcher** -> Returns **Raw Papers**
4. **Worker** -> Calls **Process Paper**
5. **Process Paper** -> Acquires **Lock**, updates **Consolidated Results** and **Stats**.

## 4. Error Handling & Rate Limiting
- `_make_request` already handles 429 errors with exponential backoff.
- The 10s sleep for CORE in `_api_worker` provides an additional layer of safety for that specific source.

## 5. Verification Plan
1. **Performance Check:** Compare execution time of Task 3 vs. Task 2 (expect significant improvement).
2. **Integrity Check:** Verify `PRISMA STATS` and the generated CSV/MD files contain the expected data.
3. **Threading Test:** Run a test case (e.g., `tests/test_threaded_engine.py`) to verify no race conditions occur.
