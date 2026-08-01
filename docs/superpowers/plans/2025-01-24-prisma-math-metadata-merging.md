# PRISMA Math & Metadata Merging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix PRISMA math logic to correctly count low-score duplicates and enhance metadata merging during deduplication.

**Architecture:** Introduce a `seen_ids` set in `run()` to track all unique papers identified. Add a helper method to merge Citations, DOI, Abstract, and Categories when duplicates are found.

**Tech Stack:** Python 3.x, pandas, requests

---

### Task 1: Update Tests for PRISMA Math and Metadata Merging

**Files:**
- Modify: `tests/test_rigor.py`

- [ ] **Step 1: Add failing test for PRISMA math with low-score duplicates**
In `tests/test_rigor.py`, add:
```python
    def test_prisma_math_low_score_duplicates(self):
        """Verify that identical low-score papers are counted as 1 excluded and 1 duplicate."""
        mock_results = [
            {"Title": "Low Score Paper", "Abstract": "X", "Source": "SourceA", "Citations": 0},
            {"Title": "Low Score Paper", "Abstract": "X", "Source": "SourceB", "Citations": 0}
        ]
        self.hunter.anchors = {"cat": ["X"]}
        self.hunter.settings["min_relevance_score"] = 10.0 # Force exclusion
        self.hunter.compiled_patterns = {"X": (re.compile(r"\bX\b"), 1.0)}
        self.hunter.anchor_patterns = {"X": re.compile(r"\bX\b")}

        # We will test the logic that should be in run()
        seen_ids = set()
        consolidated = {}
        self.hunter.stats = {"identified": {}, "duplicates_removed": 0, "excluded_score": 0, "included_final": 0}
        
        for paper in mock_results:
            source = paper.get('Source', 'Unknown')
            self.hunter.stats["identified"][source] = self.hunter.stats["identified"].get(source, 0) + 1
            dedup_id = self.hunter.generate_slug(paper["Title"])
            
            if dedup_id in seen_ids:
                self.hunter.stats["duplicates_removed"] += 1
                continue
            
            seen_ids.add(dedup_id)
            score = self.hunter.calculate_score(paper["Title"], paper["Abstract"])
            if score >= self.hunter.settings["min_relevance_score"]:
                consolidated[dedup_id] = paper
                self.hunter.stats["included_final"] += 1
            else:
                self.hunter.stats["excluded_score"] += 1
                
        self.assertEqual(self.hunter.stats["duplicates_removed"], 1)
        self.assertEqual(self.hunter.stats["excluded_score"], 1)
```

- [ ] **Step 2: Add failing test for Metadata Merging**
In `tests/test_rigor.py`, add:
```python
    def test_metadata_merging(self):
        """Verify metadata fields are merged correctly."""
        existing = {"Title": "T", "Abstract": "Short", "Citations": 10, "DOI": "", "Anchor_Category": "A1", "Tech_Category": "T1"}
        new = {"Title": "T", "Abstract": "Much Longer Abstract", "Citations": 20, "DOI": "10.1234", "Source": "S2"}
        
        # This will fail initially because the method doesn't exist
        self.hunter._merge_paper_metadata(existing, new, "A2", "T2")
        
        self.assertEqual(existing["Citations"], 20)
        self.assertEqual(existing["DOI"], "10.1234")
        self.assertEqual(existing["Abstract"], "Much Longer Abstract")
        self.assertIn("A1", existing["Anchor_Category"])
        self.assertIn("A2", existing["Anchor_Category"])
        self.assertIn("T1", existing["Tech_Category"])
        self.assertIn("T2", existing["Tech_Category"])
```

- [ ] **Step 3: Run tests to verify they fail**
Run: `python3 -m unittest tests/test_rigor.py`
Expected: FAIL (AttributeError: 'AcademicHunter' object has no attribute '_merge_paper_metadata')

### Task 2: Implement Metadata Merging and Fix `run()` Logic

**Files:**
- Modify: `src/academic_hunter.py`

- [ ] **Step 1: Add `_merge_paper_metadata` method**
Add this method to `AcademicHunter` class in `src/academic_hunter.py`:
```python
    def _merge_paper_metadata(self, existing: Dict, new: Dict, anchor_cat: str, tech_cat: str):
        """Enhances existing paper metadata with data from a duplicate."""
        if new.get('Citations', 0) > existing.get('Citations', 0):
            existing['Citations'] = new['Citations']
        
        if not existing.get('DOI') and new.get('DOI'):
            existing['DOI'] = new['DOI']
        
        if len(new.get('Abstract', '')) > len(existing.get('Abstract', '')):
            existing['Abstract'] = new['Abstract']
        
        # Merge Anchor Categories
        a_cats = set(existing.get('Anchor_Category', '').split(', '))
        a_cats.add(anchor_cat)
        existing['Anchor_Category'] = ', '.join(sorted(filter(None, a_cats)))

        # Merge Tech Categories
        t_cats = set(existing.get('Tech_Category', '').split(', '))
        t_cats.add(tech_cat)
        existing['Tech_Category'] = ', '.join(sorted(filter(None, t_cats)))
```

- [ ] **Step 2: Update `run()` method logic**
In `src/academic_hunter.py`, update the loop in `run()` to use `seen_ids` and `_merge_paper_metadata`.

```python
        seen_ids = set() # Track ALL unique papers seen in this run
        for anchor_cat, anchor_list in self.anchors.items():
            for tech_cat, tech_list in self.tech_strings.items():
                # ... existing fetch logic ...
                for paper in raw_results:
                    # 1. Track Identification
                    source = paper.get('Source', 'Unknown')
                    self.stats["identified"][source] = self.stats["identified"].get(source, 0) + 1
                    
                    title = paper.get('Title', '').strip()
                    if not title: continue
                    
                    # 2. Deduplication by Title-Slug
                    dedup_id = self.generate_slug(title)
                    
                    if dedup_id in seen_ids:
                        self.stats["duplicates_removed"] += 1
                        if dedup_id in consolidated_results:
                            self._merge_paper_metadata(consolidated_results[dedup_id], paper, anchor_cat, tech_cat)
                        continue

                    seen_ids.add(dedup_id)

                    # 3. Anchor Filtering
                    # ...
                    
                    # 4. Scoring and Exclusion
                    # ...
                    if paper["Relevance_Score"] >= self.settings.get('min_relevance_score', 0):
                        consolidated_results[dedup_id] = paper
                        self.stats["included_final"] += 1
                    else:
                        self.stats["excluded_score"] += 1
```

- [ ] **Step 3: Run tests to verify they pass**
Run: `python3 -m unittest tests/test_rigor.py`
Expected: PASS

- [ ] **Step 4: Commit changes**
```bash
git add src/academic_hunter.py tests/test_rigor.py
git commit -m "fix: prisma math for low-score duplicates and enhanced metadata merging"
```
