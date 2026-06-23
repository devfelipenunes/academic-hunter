# Task 1.1 Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve AcademicHunter robustness, performance, and test safety.

**Architecture:** Robust slug generation using `str()` casting, pre-compiled regex for term matching, and temporary directories for test configuration.

**Tech Stack:** Python, `unittest`, `re`, `json`, `tempfile`.

---

### Task 1: Robust Slug Generation

**Files:**
- Modify: `src/academic_hunter.py`
- Test: `tests/test_rigor.py`

- [ ] **Step 1: Write a failing test for non-string input in slug generation**

Add to `tests/test_rigor.py`:
```python
    def test_generate_slug_non_string(self):
        """Verify generate_slug handles non-string inputs safely."""
        self.assertEqual(self.hunter.generate_slug(None), "")
        self.assertEqual(self.hunter.generate_slug(123), "123")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests/test_rigor.py`
Expected: FAIL (AttributeError: 'int' object has no attribute 'lower')

- [ ] **Step 3: Update `generate_slug` implementation**

Modify `src/academic_hunter.py`:
```python
    def generate_slug(self, title: str) -> str:
        """Normalizes a title into a alphanumeric slug for duplicate detection."""
        if title is None: return ""
        return re.sub(r'\W+', '', str(title).lower())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests/test_rigor.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/academic_hunter.py tests/test_rigor.py
git commit -m "fix: robust slug generation for non-string inputs"
```

### Task 2: Optimized Term Matching

**Files:**
- Modify: `src/academic_hunter.py`

- [ ] **Step 1: Update `load_config` to pre-compile patterns for anchors and tech strings**

Modify `src/academic_hunter.py`:
Update `load_config` to initialize `self.anchor_patterns` and `self.tech_patterns`.

- [ ] **Step 2: Update `find_matching_terms` to use pre-compiled patterns**

Modify `src/academic_hunter.py`:
Update `find_matching_terms` to accept a dictionary or use the pre-compiled patterns from the class instance.

- [ ] **Step 3: Update `run` method to pass pre-compiled patterns**

Modify `src/academic_hunter.py`:
Update calls to `find_matching_terms`.

- [ ] **Step 4: Run existing tests to ensure no regressions**

Run: `python3 -m unittest tests/test_rigor.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/academic_hunter.py
git commit -m "perf: pre-compile regex patterns for term matching"
```

### Task 3: Safer Test Environment

**Files:**
- Modify: `tests/test_rigor.py`

- [ ] **Step 1: Update `setUp` to use `tempfile.TemporaryDirectory`**

Modify `tests/test_rigor.py`:
Use `tempfile` to create a temporary config file and output directory.

- [ ] **Step 2: Clean up test files after run**

Modify `tests/test_rigor.py`:
Ensure temporary directory is cleaned up in `tearDown`.

- [ ] **Step 3: Verify no `config.json` is created in the root during tests**

Run: `rm config.json && python3 -m unittest tests/test_rigor.py && ls config.json`
Expected: `ls: cannot access 'config.json': No such file or directory`

- [ ] **Step 4: Commit**

```bash
git add tests/test_rigor.py
git commit -m "test: use temporary directory for test configuration"
```
