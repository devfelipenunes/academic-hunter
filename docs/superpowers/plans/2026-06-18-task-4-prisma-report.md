# Automated PRISMA Report Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement automated generation of `FLUXO_PRISMA_<timestamp>.md` with a Mermaid diagram visualizing the filtering process.

**Architecture:** Add a new method `generate_prisma_report` to `AcademicHunter` that uses internal `stats` to build a Markdown file. Integrate it into the `export_results` workflow.

**Tech Stack:** Python, Pandas, Mermaid (in Markdown).

---

### Task 1: Implement `generate_prisma_report` Method

**Files:**
- Modify: `src/academic_hunter.py`

- [ ] **Step 1: Add the `generate_prisma_report` method to `AcademicHunter` class**

```python
    def generate_prisma_report(self, timestamp: str):
        """Generates a PRISMA flow report in Markdown with a Mermaid diagram."""
        total_identified = sum(self.stats["identified"].values())
        duplicates = self.stats["duplicates_removed"]
        excluded = self.stats["excluded_score"]
        final = self.stats["included_final"]
        
        prisma_file = self.output_dir / f"FLUXO_PRISMA_{timestamp}.md"
        
        sources_mermaid = "\n".join([f"        S{i}[{source}: {count}]" for i, (source, count) in enumerate(self.stats["identified"].items())])
        sources_links = "\n".join([f"        S{i} --> A" for i in range(len(self.stats["identified"]))])

        mermaid_content = f"""```mermaid
graph TD
    subgraph Sources
{sources_mermaid}
    end
{sources_links}

    A[Records identified through database searching] --> B(Total Records Identified: {total_identified})
    B --> C{{Deduplication}}
    C -->|Duplicates Removed: {duplicates}| D[Records removed after deduplication]
    C --> E[Records for Screening: {total_identified - duplicates}]
    E --> F{{Relevance Scoring}}
    F -->|Excluded by Score/Anchors: {excluded}| G[Records excluded]
    F --> H[Final Records Included: {final}]
```"""

        with open(prisma_file, 'w', encoding='utf-8') as f:
            f.write(f"# PRISMA Flow Report - {timestamp}\n\n")
            f.write("## 1. Breakdown by Source\n")
            for source, count in self.stats["identified"].items():
                f.write(f"- **{source}:** {count}\n")
            f.write(f"\n- **Total Identified:** {total_identified}\n")
            f.write(f"- **Duplicates Removed:** {duplicates}\n")
            f.write(f"- **Excluded by Score/Anchors:** {excluded}\n")
            f.write(f"- **Final Included:** {final}\n\n")
            f.write("## 2. Visual Flow (Mermaid)\n\n")
            f.write(mermaid_content)

        print(f"📊 PRISMA Report: {prisma_file}")
```

- [ ] **Step 2: Update `export_results` to call `generate_prisma_report`**

```python
    def export_results(self, results: List[Dict[str, Any]]):
        # ... (existing code)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        # ... (existing code)
        
        # After writing the MD report and CSV
        self.generate_prisma_report(timestamp)
        
        # ... (rest of the existing print statements)
```

- [ ] **Step 3: Commit implementation**

```bash
git add src/academic_hunter.py
git commit -m "feat: implement automated PRISMA report generation with Mermaid diagram"
```

### Task 2: Add Test for PRISMA Report

**Files:**
- Modify: `tests/test_rigor.py`

- [ ] **Step 1: Add `test_prisma_report_generation` to `TestAcademicRigor`**

```python
    def test_prisma_report_generation(self):
        """Verify that the PRISMA report is generated correctly."""
        self.hunter.stats = {
            "identified": {"ArXiv": 10, "Crossref": 20},
            "duplicates_removed": 5,
            "excluded_score": 10,
            "included_final": 15
        }
        
        timestamp = "TEST_TS"
        self.hunter.generate_prisma_report(timestamp)
        
        report_path = Path(self.test_dir) / f"FLUXO_PRISMA_{timestamp}.md"
        self.assertTrue(report_path.exists())
        
        content = report_path.read_text()
        self.assertIn("## 1. Breakdown by Source", content)
        self.assertIn("- **ArXiv:** 10", content)
        self.assertIn("- **Crossref:** 20", content)
        self.assertIn("Total Records Identified: 30", content)
        self.assertIn("Duplicates Removed: 5", content)
        self.assertIn("Final Records Included: 15", content)
        self.assertIn("```mermaid", content)
        self.assertIn("graph TD", content)
```

- [ ] **Step 2: Run tests to verify**

Run: `python3 tests/test_rigor.py`
Expected: ALL TESTS PASS

- [ ] **Step 3: Commit tests**

```bash
git add tests/test_rigor.py
git commit -m "test: add verification for PRISMA report generation"
```
