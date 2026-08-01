# Design Spec: PRISMA Math Fix & Enhanced Metadata Merging

**Date:** 2025-01-24
**Topic:** Task 2.1: Fix PRISMA Math & Enhance Deduplication

## 1. Problem Statement
The current `AcademicHunter` has two main issues:
1. **PRISMA Math Flaw:** Low-score duplicates are miscounted. If a paper fails the relevance score check, it's counted as "Excluded (Score)". If the same paper appears again, it's NOT counted as a duplicate because it wasn't added to `consolidated_results`.
2. **Basic Metadata Merging:** Only citations are updated during deduplication. We need to merge more fields (DOI, Abstract, Categories) to ensure the final dataset has the highest quality information.

## 2. Proposed Solution

### 2.1 PRISMA Logic Refinement
We will introduce a `seen_ids` set in the `run()` method to track every unique paper identified (by title-slug) during the entire mining process, regardless of whether it passes the filters.

**New Logic Flow:**
1.  **Identify:** Increment source stats.
2.  **Deduplicate Check:** 
    -   If `dedup_id` in `seen_ids`:
        -   Increment `duplicates_removed`.
        -   If `dedup_id` is also in `consolidated_results`, call `merge_metadata()`.
        -   `continue` to next paper.
    -   Else:
        -   Add `dedup_id` to `seen_ids`.
3.  **Anchor Filter:** If it fails, `continue`.
4.  **Scoring:** 
    -   If `score >= min_relevance_score`:
        -   Add to `consolidated_results`.
        -   Increment `included_final`.
    -   Else:
        -   Increment `excluded_score`.

This ensures that:
-   `identified` = `duplicates_removed` + `excluded_anchor` (not explicitly tracked but implicit) + `excluded_score` + `included_final`.
-   Identical low-score papers are counted as 1 Excluded and N-1 Duplicates.

### 2.2 Metadata Merging
A new helper method `merge_metadata(existing_paper, new_paper, anchor_cat, tech_cat)` will be added.

**Merging Rules:**
-   **Citations:** Keep the maximum value.
-   **DOI:** Use `new_paper`'s DOI if `existing_paper`'s is missing.
-   **Abstract:** Use `new_paper`'s abstract if it is longer.
-   **Anchor_Category:** Append `anchor_cat` if not already present.
-   **Tech_Category:** Append `tech_cat` if not already present.

### 2.3 Unit Testing
Update `tests/test_rigor.py` to:
1.  Verify that two identical low-score papers result in 1 `excluded_score` and 1 `duplicates_removed`.
2.  Verify that metadata (Citations, DOI, Abstract, Categories) are correctly updated/merged.

## 3. Implementation Details

### `AcademicHunter.run()` changes:
```python
seen_ids = set() # Track ALL unique papers seen in this run
for anchor_cat, anchor_list in self.anchors.items():
    for tech_cat, tech_list in self.tech_strings.items():
        # ... fetch raw_results ...
        for paper in raw_results:
            # 1. Track Identification
            # ...
            dedup_id = self.generate_slug(title)
            
            if dedup_id in seen_ids:
                self.stats["duplicates_removed"] += 1
                if dedup_id in consolidated_results:
                    self._merge_paper_metadata(consolidated_results[dedup_id], paper, anchor_cat, tech_cat)
                continue
            
            seen_ids.add(dedup_id)
            # ... anchor check ...
            # ... scoring ...
            if paper["Relevance_Score"] >= min_score:
                consolidated_results[dedup_id] = paper
                self.stats["included_final"] += 1
            else:
                self.stats["excluded_score"] += 1
```

### New helper method `_merge_paper_metadata`:
```python
def _merge_paper_metadata(self, existing: Dict, new: Dict, anchor_cat: str, tech_cat: str):
    # Citations
    if new.get('Citations', 0) > existing.get('Citations', 0):
        existing['Citations'] = new['Citations']
    
    # DOI
    if not existing.get('DOI') and new.get('DOI'):
        existing['DOI'] = new['DOI']
    
    # Abstract
    if len(new.get('Abstract', '')) > len(existing.get('Abstract', '')):
        existing['Abstract'] = new['Abstract']
    
    # Categories (comma-separated unique)
    existing_anchors = set(existing.get('Anchor_Category', '').split(', '))
    existing_anchors.add(anchor_cat)
    existing['Anchor_Category'] = ', '.join(sorted(filter(None, existing_anchors)))

    existing_tech = set(existing.get('Tech_Category', '').split(', '))
    existing_tech.add(tech_cat)
    existing['Tech_Category'] = ', '.join(sorted(filter(None, existing_tech)))
```

## 4. Success Criteria
-   `duplicates_removed` correctly reflects all redundant papers, including those with low scores.
-   `excluded_score` only counts unique papers that failed the score threshold.
-   The final dataset contains merged metadata from duplicate records.
-   `tests/test_rigor.py` passes with the new logic.
