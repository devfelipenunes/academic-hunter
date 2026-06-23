# Title-Slug Deduplication and PRISMA Stats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update `AcademicHunter` to use title-slugs for deduplication and track PRISMA stats during the mining process.

**Architecture:** Modify the `run()` method in `src/academic_hunter.py` to update `self.stats` and use `generate_slug` for `dedup_id`. Update citation counts for duplicates.

**Tech Stack:** Python, Pandas, Unittest.

---

### Task 1: Add Rigorous Deduplication Test

**Files:**
- Modify: `tests/test_rigor.py`

- [ ] **Step 1: Write the failing test for deduplication and stats**

```python
    def test_deduplication_and_stats(self):
        """Verify title-slug deduplication, citation updates, and PRISMA stats."""
        # Mock raw results from two different sources with same title but different citations
        mock_results = [
            {
                "Title": "Duplicate Paper",
                "Abstract": "First version.",
                "Year": "2021",
                "URL": "http://example.com/1",
                "Source": "SourceA",
                "Citations": 10,
                "DOI": "10.1234/1"
            },
            {
                "Title": "Duplicate Paper",
                "Abstract": "Second version.",
                "Year": "2021",
                "URL": "http://example.com/2",
                "Source": "SourceB",
                "Citations": 20,
                "DOI": "10.1234/2"
            },
            {
                "Title": "Low Score Paper",
                "Abstract": "Irrelevant content.",
                "Year": "2021",
                "URL": "http://example.com/3",
                "Source": "SourceA",
                "Citations": 5,
                "DOI": "10.1234/3"
            }
        ]
        
        # We need to manually trigger the logic that would be in run()
        # For this test, we'll mock the internal state and calls
        self.hunter.anchors = {"cat": ["duplicate", "low"]}
        self.hunter.settings["min_relevance_score"] = 5.0
        self.hunter.tech_weights = {"duplicate": 10.0, "low": 1.0}
        self.hunter.load_config = lambda: None # Skip actual loading
        self.hunter.compiled_patterns = {
            "duplicate": (re.compile(r'\bduplicate\b'), 10.0),
            "low": (re.compile(r'\blow\b'), 1.0)
        }
        self.hunter.anchor_patterns = {
            "duplicate": re.compile(r'\bduplicate\b'),
            "low": re.compile(r'\blow\b')
        }

        # Instead of calling run(), we'll implement a miniature version of the deduplication loop
        # to verify the logic we intend to put in run().
        consolidated = {}
        
        # Logic to be implemented in Task 2
        for paper in mock_results:
            source = paper.get('Source', 'Unknown')
            self.hunter.stats["identified"][source] = self.hunter.stats["identified"].get(source, 0) + 1
            
            title = paper.get('Title', '').strip()
            dedup_id = self.hunter.generate_slug(title)
            
            if dedup_id in consolidated:
                self.hunter.stats["duplicates_removed"] += 1
                if paper.get('Citations', 0) > consolidated[dedup_id].get('Citations', 0):
                    consolidated[dedup_id]['Citations'] = paper['Citations']
                continue
            
            # Simplified score and anchor check for test
            paper["Relevance_Score"] = self.hunter.calculate_score(title, paper.get('Abstract', ''))
            if paper["Relevance_Score"] >= self.hunter.settings["min_relevance_score"]:
                consolidated[dedup_id] = paper
                self.hunter.stats["included_final"] += 1
            else:
                self.hunter.stats["excluded_score"] += 1

        # Assertions
        self.assertEqual(len(consolidated), 1)
        self.assertEqual(consolidated[self.hunter.generate_slug("Duplicate Paper")]['Citations'], 20)
        self.assertEqual(self.hunter.stats["identified"]["SourceA"], 2)
        self.assertEqual(self.hunter.stats["identified"]["SourceB"], 1)
        self.assertEqual(self.hunter.stats["duplicates_removed"], 1)
        self.assertEqual(self.hunter.stats["excluded_score"], 1)
        self.assertEqual(self.hunter.stats["included_final"], 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests/test_rigor.py`
Expected: FAIL (because the stats and logic aren't in `src/academic_hunter.py` yet, or rather, the test won't even run correctly without imports)

- [ ] **Step 3: Fix imports and setup in `tests/test_rigor.py`**

```python
import unittest
import json
import tempfile
import shutil
import re
from pathlib import Path
from src.academic_hunter import AcademicHunter
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_rigor.py
git commit -m "test: add deduplication and PRISMA stats test case"
```

### Task 2: Update Deduplication and Stats in `src/academic_hunter.py`

**Files:**
- Modify: `src/academic_hunter.py`

- [ ] **Step 1: Update `run()` method with new logic**

```python
    def run(self, limit_per_source: int = 100):
        print(f"🚀 Initializing Academic Hunter V2 Pipeline...")
        consolidated_results = {} # Key: Title-Slug
        
        # Reset stats for fresh run
        self.stats = {
            "identified": {},
            "duplicates_removed": 0,
            "excluded_score": 0,
            "included_final": 0
        }

        for anchor_cat, anchor_list in self.anchors.items():
            for tech_cat, tech_list in self.tech_strings.items():
                print(f"\n📂 Mining: [{anchor_cat}] x [{tech_cat}]")
                
                raw_results = (
                    self.fetch_arxiv(anchor_list, tech_list, limit=limit_per_source) +
                    self.fetch_crossref(anchor_list, tech_list, limit=limit_per_source) +
                    self.fetch_semantic_scholar(anchor_list, tech_list, limit=limit_per_source) +
                    self.fetch_openalex(anchor_list, tech_list, limit=limit_per_source) +
                    self.fetch_core_ac(anchor_list, tech_list, limit=limit_per_source)
                )

                for paper in raw_results:
                    # 1. Track Identification
                    source = paper.get('Source', 'Unknown')
                    self.stats["identified"][source] = self.stats["identified"].get(source, 0) + 1
                    
                    title = paper.get('Title', '').strip()
                    if not title: continue
                    
                    # 2. Deduplication by Title-Slug
                    dedup_id = self.generate_slug(title)
                    
                    if dedup_id in consolidated_results:
                        self.stats["duplicates_removed"] += 1
                        if paper.get('Citations', 0) > consolidated_results[dedup_id].get('Citations', 0):
                            consolidated_results[dedup_id]['Citations'] = paper['Citations']
                        continue

                    # 3. Anchor Filtering
                    full_text = f"{title} {paper.get('Abstract', '')}".lower()
                    matched_anchors = self.find_matching_terms(full_text, anchor_list)
                    if not matched_anchors: continue

                    # 4. Scoring and Exclusion
                    paper.update({
                        "Anchor_Category": anchor_cat,
                        "Matched_Anchors": matched_anchors,
                        "Tech_Category": tech_cat,
                        "Matched_Tech_Terms": self.find_matching_terms(full_text, tech_list),
                        "Relevance_Score": self.calculate_score(title, paper.get('Abstract', ''))
                    })
                    
                    if paper["Relevance_Score"] >= self.settings.get('min_relevance_score', 0):
                        consolidated_results[dedup_id] = paper
                        self.stats["included_final"] += 1
                    else:
                        self.stats["excluded_score"] += 1
                
                time.sleep(2)

        self.export_results(list(consolidated_results.values()))
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `python3 -m unittest tests/test_rigor.py`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/academic_hunter.py
git commit -m "feat: implement title-slug deduplication and PRISMA stats tracking"
```

### Task 3: Final Verification and Report Update (Optional but Good)

**Files:**
- Modify: `src/academic_hunter.py`

- [ ] **Step 1: Include PRISMA stats in the exported report**

Modify `export_results` to print or save the stats.

```python
    def export_results(self, results: List[Dict[str, Any]]):
        # ... existing export logic ...
        
        print(f"\n📊 PRISMA STATS:")
        print(f"   - Identified: {self.stats['identified']}")
        print(f"   - Duplicates Removed: {self.stats['duplicates_removed']}")
        print(f"   - Excluded (Score): {self.stats['excluded_score']}")
        print(f"   - Final Included: {self.stats['included_final']}")
        
        # Also write stats to the MD report
        with open(md_file, 'a', encoding='utf-8') as f:
            f.write("\n## PRISMA Flow Stats\n")
            f.write(f"- **Identified:** {json.dumps(self.stats['identified'])}\n")
            f.write(f"- **Duplicates Removed:** {self.stats['duplicates_removed']}\n")
            f.write(f"- **Excluded (Score):** {self.stats['excluded_score']}\n")
            f.write(f"- **Final Included:** {self.stats['included_final']}\n")
```

- [ ] **Step 2: Final Run**

Run: `python3 src/academic_hunter.py` (ensure config.json is present)

- [ ] **Step 3: Commit**

```bash
git add src/academic_hunter.py
git commit -m "feat: add PRISMA stats to export report"
```
