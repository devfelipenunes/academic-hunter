# Academic Hunter Rigor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement robust title-based deduplication, peer-review status detection, and automated PRISMA flow reporting in `academic_hunter.py`.

**Architecture:** Extend the `AcademicHunter` class with a `stats` tracker for PRISMA metrics, implement a title-normalization slug for grouping, and add classification logic for peer-review status based on API source and metadata.

**Tech Stack:** Python, Pandas, Regex, Requests.

---

### Task 1: Setup PRISMA Tracking & Title Normalization

**Files:**
- Modify: `src/academic_hunter.py`
- Create: `tests/test_rigor.py`

- [ ] **Step 1: Write tests for title normalization**

```python
import pytest
import re
from src.academic_hunter import AcademicHunter

def test_title_normalization():
    hunter = AcademicHunter()
    title1 = "Blockchain & ISO 20022: A Survey!"
    title2 = "blockchain iso 20022 a survey"
    slug1 = hunter.generate_slug(title1)
    slug2 = hunter.generate_slug(title2)
    assert slug1 == slug2
    assert slug1 == "blockchainiso20022asurvey"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_rigor.py -v`
Expected: FAIL (AttributeError: 'AcademicHunter' object has no attribute 'generate_slug')

- [ ] **Step 3: Implement `generate_slug` and initialize `self.stats`**

```python
# In src/academic_hunter.py

# In __init__:
self.stats = {
    "identified": {}, # Source: Count
    "duplicates_removed": 0,
    "excluded_score": 0,
    "included_final": 0
}

def generate_slug(self, title: str) -> str:
    if not title: return ""
    # Remove non-alphanumeric, convert to lower
    return re.sub(r'\W+', '', title.lower())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_rigor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/academic_hunter.py tests/test_rigor.py
git commit -m "refactor: add title normalization and stats tracking"
```

---

### Task 2: Implement Title-Slug Deduplication

**Files:**
- Modify: `src/academic_hunter.py`

- [ ] **Step 1: Update `run` method logic to use slugs for consolidation**

```python
# In src/academic_hunter.py -> run() method

# Change:
# dedup_id = doi if doi else re.sub(r'\W+', '', title.lower())
# To:
dedup_id = self.generate_slug(title)

# Log raw counts for PRISMA
source = paper.get('Source', 'Unknown')
self.stats["identified"][source] = self.stats["identified"].get(source, 0) + 1

if dedup_id in consolidated_results:
    self.stats["duplicates_removed"] += 1
    # Keep the one with more citations
    if paper.get('Citations', 0) > consolidated_results[dedup_id].get('Citations', 0):
        consolidated_results[dedup_id].update(paper) # Update with potentially better data
    continue
```

- [ ] **Step 2: Verify deduplication with a mock run or test**

(Manual check of `self.stats["duplicates_removed"]` during a dry run)

- [ ] **Step 3: Commit**

```bash
git add src/academic_hunter.py
git commit -m "feat: implement title-slug based deduplication"
```

---

### Task 3: Peer-Review & Venue Detection

**Files:**
- Modify: `src/academic_hunter.py`

- [ ] **Step 1: Implement `detect_peer_review` and `extract_venue`**

```python
# In src/academic_hunter.py

def detect_peer_review(self, paper: Dict[str, Any]) -> str:
    source = paper.get('Source')
    # Crossref is high authority
    if source == "Crossref": return "Yes"
    
    # OpenAlex types
    if source == "OpenAlex":
        # Note: In current code, we might need to store 'type' in paper dict during fetch
        # Let's assume we update fetchers to include 'Type'
        ptype = paper.get('Type', '').lower()
        if 'article' in ptype or 'proceedings' in ptype: return "Yes"
    
    if source == "ArXiv": return "No (Preprint)"
    
    return "Likely"

def extract_venue(self, paper: Dict[str, Any]) -> str:
    # This will require updating fetchers to capture journal/conf names
    return paper.get('Venue', 'N/A')
```

- [ ] **Step 2: Update API Fetchers (Crossref, OpenAlex, Semantic Scholar) to capture Venue and Type**

```python
# Example for OpenAlex:
articles.append({
    "Title": i.get('display_name'),
    "Abstract": abstract_text,
    "Year": i.get('publication_year'),
    "URL": i.get('doi') or i.get('id'),
    "Source": "OpenAlex",
    "Citations": i.get('cited_by_count', 0),
    "DOI": doi_clean,
    "Type": i.get('type'), # NEW
    "Venue": i.get('primary_location', {}).get('source', {}).get('display_name', 'N/A') # NEW
})
```

- [ ] **Step 3: Apply detection during result consolidation**

```python
# In run() method, before adding to consolidated_results:
paper["Peer_Reviewed"] = self.detect_peer_review(paper)
paper["Venue"] = self.extract_venue(paper)
```

- [ ] **Step 4: Commit**

```bash
git add src/academic_hunter.py
git commit -m "feat: add peer-review and venue detection"
```

---

### Task 4: Automated PRISMA Report Generation

**Files:**
- Modify: `src/academic_hunter.py`

- [ ] **Step 1: Implement `generate_prisma_report`**

```python
# In src/academic_hunter.py

def generate_prisma_report(self, timestamp: str):
    total_identified = sum(self.stats["identified"].values())
    prisma_file = self.output_dir / f"FLUXO_PRISMA_{timestamp}.md"
    
    with open(prisma_file, 'w', encoding='utf-8') as f:
        f.write(f"# PRISMA Flow Report - {timestamp}\n\n")
        f.write("## 1. Identification\n")
        for src, count in self.stats["identified"].items():
            f.write(f"- **{src}:** {count} records\n")
        f.write(f"**Total Identified:** {total_identified}\n\n")
        
        f.write("## 2. Screening & Deduplication\n")
        f.write(f"- **Duplicates Removed:** {self.stats['duplicates_removed']}\n")
        f.write(f"- **Records Excluded (Low Score):** {self.stats['excluded_score']}\n\n")
        
        f.write("## 3. Final Inclusion\n")
        f.write(f"- **Total Included in Dataset:** {self.stats['included_final']}\n\n")
        
        f.write("## 4. Visual Flow (Mermaid)\n")
        f.write("```mermaid\ngraph TD\n")
        f.write(f"    A[Identification: {total_identified} records] --> B[Deduplication: -{self.stats['duplicates_removed']} duplicates]\n")
        f.write(f"    B --> C[Screening: {total_identified - self.stats['duplicates_removed']} analyzed]\n")
        f.write(f"    C --> D[Excluded Score: -{self.stats['excluded_score']} records]\n")
        f.write(f"    D --> E[Inclusion Final: {self.stats['included_final']} articles]\n")
        f.write("```\n")
```

- [ ] **Step 2: Call `generate_prisma_report` in `export_results`**

- [ ] **Step 3: Commit**

```bash
git add src/academic_hunter.py
git commit -m "feat: implement automated PRISMA report generation"
```

---

### Task 5: Final Validation Run

- [ ] **Step 1: Execute a full pipeline run**

Run: `python3 src/academic_hunter.py`

- [ ] **Step 2: Inspect results**
- Verify `results/academic_dataset_...csv` has the new columns.
- Verify `results/FLUXO_PRISMA_...md` exists and has correct numbers.
- Verify no visual duplicates exist in the CSV.

- [ ] **Step 3: Final Commit**

```bash
git commit -am "chore: final validation of rigor updates"
```
