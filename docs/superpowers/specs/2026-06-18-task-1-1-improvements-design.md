# Design Doc: Task 1.1 Minor Improvements from Code Review

Address feedback from Task 1 code quality review focusing on robustness, performance, and test safety.

## 1. Robust Slug Generation
- **Goal:** Prevent crashes on non-string inputs in `generate_slug`.
- **Location:** `src/academic_hunter.py`
- **Action:** Update `generate_slug` to use `str(title).lower()`.

## 2. Regex Optimization
- **Goal:** Improve performance by pre-compiling regex patterns for anchors and technical terms.
- **Location:** `src/academic_hunter.py`
- **Action:**
    - Modify `load_config` to pre-compile patterns for all terms in `self.anchors` and `self.tech_strings`.
    - Create a mapping structure to store these compiled patterns.
    - Update `find_matching_terms` to use these pre-compiled patterns.

## 3. Safer Test Environment
- **Goal:** Prevent tests from overwriting or depending on the local `config.json`.
- **Location:** `tests/test_rigor.py`
- **Action:**
    - Use `unittest.mock` or a temporary directory to provide a safe configuration for `AcademicHunter` during tests.
    - Ensure `config.json` is not created in the root directory during test runs.

## Self-Review
- **Placeholder scan:** None.
- **Internal consistency:** Matches requested improvements.
- **Scope check:** Appropriately scoped for a minor update.
- **Ambiguity check:** Implementation details for regex pre-compilation need to handle the nested structure of `self.anchors` and `self.tech_strings`.
