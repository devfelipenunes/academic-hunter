# Design Spec: Title-Slug Deduplication and PRISMA Stats

## Overview
Update the `AcademicHunter` pipeline to use a more robust title-slug based deduplication strategy and accurately track PRISMA (Preferred Reporting Items for Systematic Reviews and Meta-Analyses) statistics throughout the mining process.

## Problem Statement
The current deduplication logic relies on DOI if available, falling back to title-slugs. However, consistent deduplication is better achieved by using title-slugs globally. Furthermore, the PRISMA stats initialized in the constructor are not currently being updated during the `run()` execution, making it impossible to report on the search rigor.

## Proposed Changes

### 1. src/academic_hunter.py

#### Deduplication Strategy
- Modify `run()` to generate `dedup_id` exclusively using `self.generate_slug(title)`.
- When a duplicate is encountered:
    - Increment `self.stats["duplicates_removed"]`.
    - Update the existing record if the new record has a higher `Citations` count.

#### PRISMA Stats Implementation
- **`identified`**: Track total records found per source (e.g., `{"ArXiv": 50, "Crossref": 30}`).
- **`duplicates_removed`**: Track total duplicates found during consolidation.
- **`excluded_score`**: Track records that were discarded because they fell below the `min_relevance_score`.
- **`included_final`**: Final count of records exported.

#### Filtering Logic
- Ensure `min_relevance_score` check correctly increments `excluded_score`.
- Ensure anchor matching check correctly filters results (though currently not explicitly tracked in PRISMA stats in the prompt, we will maintain existing behavior).

### 2. tests/test_rigor.py
- Add a new test method `test_deduplication_and_stats` that:
    - Mocks a set of `raw_results` with overlapping titles and varying citations.
    - Runs a controlled version of the deduplication logic (or calls a method that encapsulates it).
    - Asserts that the final consolidated count and stats are correct.

## Architecture and Data Flow
1. **Fetch**: Papers are fetched from various APIs.
2. **Identify**: Increment `stats["identified"]` per source.
3. **Deduplicate**: Generate title-slug. If exists, update citations and increment `stats["duplicates_removed"]`.
4. **Anchor Filter**: Filter by anchor terms.
5. **Score Filter**: Calculate score. If < `min_relevance_score`, increment `stats["excluded_score"]`.
6. **Include**: Increment `stats["included_final"]`.

## Error Handling
- Null or empty titles should be skipped early and not affect stats or deduplication.
- Non-string titles should be handled safely by `generate_slug`.

## Success Criteria
- [ ] `consolidated_results` contains unique papers based on title-slug.
- [ ] Citation counts in `consolidated_results` reflect the maximum found across all sources for a given paper.
- [ ] `self.stats` is fully populated after a `run()` call.
- [ ] New test case passes consistently.
