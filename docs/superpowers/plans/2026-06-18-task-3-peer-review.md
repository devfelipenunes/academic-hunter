# Task 3: Peer-Review & Venue Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement status classification for Peer-Review and extract publication Venue across all integrated APIs.

**Architecture:** Update fetcher methods to extract `Type` and `Venue`. Implement a heuristic-based `detect_peer_review` method. Update consolidation and export logic to include these fields.

**Tech Stack:** Python, requests, pandas.

---

### Task 1: Update ArXiv Fetcher

**Files:**
- Modify: `src/academic_hunter.py`

- [ ] **Step 1: Update `fetch_arxiv` to include Type and Venue**

```python
<<<<
                return [{
                    "Title": e.find('atom:title', ns).text.strip().replace('\n', ' '),
                    "Abstract": e.find('atom:summary', ns).text.strip().replace('\n', ' '), 
                    "Year": e.find('atom:published', ns).text[:4],
                    "URL": e.find('atom:id', ns).text, 
                    "Source": "ArXiv",
                    "Citations": 0
                } for e in root.findall('atom:entry', ns)]
====
                return [{
                    "Title": e.find('atom:title', ns).text.strip().replace('\n', ' '),
                    "Abstract": e.find('atom:summary', ns).text.strip().replace('\n', ' '), 
                    "Year": e.find('atom:published', ns).text[:4],
                    "URL": e.find('atom:id', ns).text, 
                    "Source": "ArXiv",
                    "Citations": 0,
                    "Type": "preprint",
                    "Venue": "ArXiv"
                } for e in root.findall('atom:entry', ns)]
>>>>
```

- [ ] **Step 2: Commit**

```bash
git add src/academic_hunter.py
git commit -m "feat: add Type and Venue to ArXiv fetcher"
```

---

### Task 2: Update Crossref Fetcher

**Files:**
- Modify: `src/academic_hunter.py`

- [ ] **Step 1: Update `fetch_crossref` to include Type and Venue**

```python
<<<<
            return [{
                "Title": i.get('title', [""])[0],
                "Abstract": i.get('abstract', ""), 
                "Year": i.get('published-print', {}).get('date-parts', [[0]])[0][0] if 'published-print' in i else "N/A", 
                "URL": i.get('URL', ""),
                "Source": "Crossref",
                "Citations": i.get('is-referenced-by-count', 0),
                "DOI": i.get('DOI')
            } for i in resp.get('message', {}).get('items', [])]
====
            return [{
                "Title": i.get('title', [""])[0],
                "Abstract": i.get('abstract', ""), 
                "Year": i.get('published-print', {}).get('date-parts', [[0]])[0][0] if 'published-print' in i else "N/A", 
                "URL": i.get('URL', ""),
                "Source": "Crossref",
                "Citations": i.get('is-referenced-by-count', 0),
                "DOI": i.get('DOI'),
                "Type": i.get('type'),
                "Venue": i.get('container-title', ["Unknown Venue"])[0]
            } for i in resp.get('message', {}).get('items', [])]
>>>>
```

- [ ] **Step 2: Commit**

```bash
git add src/academic_hunter.py
git commit -m "feat: add Type and Venue to Crossref fetcher"
```

---

### Task 3: Update Semantic Scholar Fetcher

**Files:**
- Modify: `src/academic_hunter.py`

- [ ] **Step 1: Update `fetch_semantic_scholar` to include Type and Venue**

```python
<<<<
        params = {
            "query": query, "limit": limit, "year": f"{start_year}-", 
            "fields": "title,abstract,url,year,citationCount,publicationTypes,externalIds"
        }
====
        params = {
            "query": query, "limit": limit, "year": f"{start_year}-", 
            "fields": "title,abstract,url,year,citationCount,publicationTypes,externalIds,journal,venue"
        }
>>>>
```

```python
<<<<
                    articles.append({
                        "Title": i.get('title'),
                        "Abstract": i.get('abstract') or "",
                        "Year": i.get('year'), 
                        "URL": i.get('url'),
                        "Source": "SemanticScholar",
                        "Citations": i.get('citationCount', 0), 
                        "DOI": i.get('externalIds', {}).get('DOI')
                    })
====
                    articles.append({
                        "Title": i.get('title'),
                        "Abstract": i.get('abstract') or "",
                        "Year": i.get('year'), 
                        "URL": i.get('url'),
                        "Source": "SemanticScholar",
                        "Citations": i.get('citationCount', 0), 
                        "DOI": i.get('externalIds', {}).get('DOI'),
                        "Type": ", ".join(pub_types) if pub_types else "N/A",
                        "Venue": i.get('journal', {}).get('name') or i.get('venue') or "Unknown Venue"
                    })
>>>>
```

- [ ] **Step 2: Commit**

```bash
git add src/academic_hunter.py
git commit -m "feat: add Type and Venue to Semantic Scholar fetcher"
```

---

### Task 4: Update CORE Fetcher

**Files:**
- Modify: `src/academic_hunter.py`

- [ ] **Step 1: Update `fetch_core_ac` to include Type and Venue**

```python
<<<<
            return [{
                "Title": i.get('title'),
                "Abstract": i.get('abstract'),
                "Year": i.get('yearPublished'), 
                "URL": f"https://core.ac.uk/works/{i.get('id')}",
                "Source": "CORE",
                "Citations": 0,
                "DOI": i.get('doi')
            } for i in resp.get('results', [])]
====
            return [{
                "Title": i.get('title'),
                "Abstract": i.get('abstract'),
                "Year": i.get('yearPublished'), 
                "URL": f"https://core.ac.uk/works/{i.get('id')}",
                "Source": "CORE",
                "Citations": 0,
                "DOI": i.get('doi'),
                "Type": i.get('type'),
                "Venue": i.get('publisher') or (i.get('journals', [{}])[0].get('title') if i.get('journals') else "Unknown Venue")
            } for i in resp.get('results', [])]
>>>>
```

- [ ] **Step 2: Commit**

```bash
git add src/academic_hunter.py
git commit -m "feat: add Type and Venue to CORE fetcher"
```

---

### Task 5: Update OpenAlex Fetcher

**Files:**
- Modify: `src/academic_hunter.py`

- [ ] **Step 1: Update `fetch_openalex` to include Type and Venue**

```python
<<<<
                articles.append({
                    "Title": i.get('display_name'),
                    "Abstract": abstract_text,
                    "Year": i.get('publication_year'),
                    "URL": i.get('doi') or i.get('id'),
                    "Source": "OpenAlex",
                    "Citations": i.get('cited_by_count', 0),
                    "DOI": doi_clean
                })
====
                articles.append({
                    "Title": i.get('display_name'),
                    "Abstract": abstract_text,
                    "Year": i.get('publication_year'),
                    "URL": i.get('doi') or i.get('id'),
                    "Source": "OpenAlex",
                    "Citations": i.get('cited_by_count', 0),
                    "DOI": doi_clean,
                    "Type": i.get('type'),
                    "Venue": i.get('primary_location', {}).get('source', {}).get('display_name') or "Unknown Venue"
                })
>>>>
```

- [ ] **Step 2: Commit**

```bash
git add src/academic_hunter.py
git commit -m "feat: add Type and Venue to OpenAlex fetcher"
```

---

### Task 6: Implement Peer-Review Detection

**Files:**
- Modify: `src/academic_hunter.py`

- [ ] **Step 1: Implement `detect_peer_review` method**

```python
    def detect_peer_review(self, paper: Dict[str, Any]) -> str:
        """Heuristic to classify peer-review status based on source and type."""
        source = paper.get('Source')
        doc_type = str(paper.get('Type', '')).lower()
        
        if source == "Crossref":
            return "Yes"
        if source == "ArXiv":
            return "No (Preprint)"
        if source in ["OpenAlex", "CORE"]:
            # Check for journal articles or conference proceedings
            if any(t in doc_type for t in ["article", "proceedings", "journal"]):
                return "Yes"
        if source == "SemanticScholar":
            # Semantic Scholar uses list of strings for publicationTypes
            if "journalarticle" in doc_type.replace(" ", ""):
                return "Likely"
        
        return "N/A"
```

- [ ] **Step 2: Commit**

```bash
git add src/academic_hunter.py
git commit -m "feat: implement detect_peer_review heuristic"
```

---

### Task 7: Update Metadata Merging

**Files:**
- Modify: `src/academic_hunter.py`

- [ ] **Step 1: Update `_merge_paper_metadata` to handle Venue and Peer_Reviewed**

```python
    def _merge_paper_metadata(self, existing: Dict, new: Dict, anchor_cat: str, tech_cat: str):
        """Enhances existing paper metadata with data from a duplicate."""
        # ... (existing logic)
        
        # New: Merge Venue and Peer_Reviewed
        if existing.get('Venue') in [None, "", "Unknown Venue"] and new.get('Venue'):
            existing['Venue'] = new['Venue']
        
        # Priority for Peer_Reviewed: Yes > Likely > No (Preprint) > N/A
        priority = {"Yes": 3, "Likely": 2, "No (Preprint)": 1, "N/A": 0}
        new_status = self.detect_peer_review(new)
        existing_status = existing.get('Peer_Reviewed', "N/A")
        
        if priority.get(new_status, 0) > priority.get(existing_status, 0):
            existing['Peer_Reviewed'] = new_status
```

- [ ] **Step 2: Commit**

```bash
git add src/academic_hunter.py
git commit -m "feat: update metadata merging for Venue and Peer_Reviewed"
```

---

### Task 8: Update `run()` and `export_results`

**Files:**
- Modify: `src/academic_hunter.py`

- [ ] **Step 1: Apply `detect_peer_review` in `run()`**

```python
<<<<
                    # 4. Scoring and Exclusion
                    paper.update({
                        "Anchor_Category": anchor_cat,
====
                    # 4. Scoring and Exclusion
                    paper.update({
                        "Peer_Reviewed": self.detect_peer_review(paper),
                        "Anchor_Category": anchor_cat,
>>>>
```

- [ ] **Step 2: Update `export_results` report format**

```python
<<<<
                f.write(f"### {row['Title']} (Score: {row['Relevance_Score']})\n")
                f.write(f"- **Year:** {row['Year']} | **Citations:** {row['Citations']}\n")
                f.write(f"- **Source:** {row['Source']} | **DOI:** {row['DOI']}\n")
====
                f.write(f"### {row['Title']} (Score: {row['Relevance_Score']})\n")
                f.write(f"- **Year:** {row['Year']} | **Citations:** {row['Citations']} | **Peer-Reviewed:** {row.get('Peer_Reviewed', 'N/A')}\n")
                f.write(f"- **Source:** {row['Source']} | **Venue:** {row.get('Venue', 'N/A')} | **DOI:** {row.get('DOI', 'N/A')}\n")
>>>>
```

- [ ] **Step 3: Commit**

```bash
git add src/academic_hunter.py
git commit -m "feat: integrate Peer_Reviewed and Venue into run and report"
```

---

### Task 9: Verify with Tests

**Files:**
- Modify: `tests/test_rigor.py`

- [ ] **Step 1: Add `test_peer_review_detection`**

```python
    def test_peer_review_detection(self):
        """Verify peer-review classification heuristic."""
        # ArXiv -> No (Preprint)
        paper_arxiv = {"Source": "ArXiv", "Type": "preprint"}
        self.assertEqual(self.hunter.detect_peer_review(paper_arxiv), "No (Preprint)")
        
        # Crossref -> Yes
        paper_crossref = {"Source": "Crossref", "Type": "journal-article"}
        self.assertEqual(self.hunter.detect_peer_review(paper_crossref), "Yes")
        
        # OpenAlex article -> Yes
        paper_oa = {"Source": "OpenAlex", "Type": "article"}
        self.assertEqual(self.hunter.detect_peer_review(paper_oa), "Yes")
        
        # Semantic Scholar JournalArticle -> Likely
        paper_s2 = {"Source": "SemanticScholar", "Type": "JournalArticle"}
        self.assertEqual(self.hunter.detect_peer_review(paper_s2), "Likely")
        
        # Random N/A
        paper_none = {"Source": "Unknown", "Type": "book"}
        self.assertEqual(self.hunter.detect_peer_review(paper_none), "N/A")
```

- [ ] **Step 2: Run tests**

Run: `python3 tests/test_rigor.py`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_rigor.py
git commit -m "test: add peer-review detection test"
```
