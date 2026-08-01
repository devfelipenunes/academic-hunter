# Design Spec: Academic Hunter V2 - Academic Rigor & Deduplication

**Date:** 2026-06-18
**Author:** Gemini CLI
**Status:** Draft - Pending User Review
**Topic:** deduplication, peer-review validation, and PRISMA flow generation.

## 1. Goal
Enhance `academic_hunter.py` with academic rigor by implementing robust deduplication, peer-review status detection, and automated PRISMA-compliant reporting.

## 2. Methodology (4-Phase Protocol)
The system will follow a structured academic search protocol to ensure transparency and reproducibility:

### Phase I: Identification
- **Action:** Multi-base API harvesting (OpenAlex, Crossref, ArXiv, Semantic Scholar, CORE).
- **Metric:** Log raw result counts per source.

### Phase II: Deduplication
- **Action:** Title-based normalization (removal of symbols, accents, extra spaces, and case folding).
- **Rule:** If "Normalized Title" matches, keep the entry with the highest citation count or the most complete metadata (prioritizing Crossref/OpenAlex over Zenodo/ArXiv).

### Phase III: Screening
- **Action:** Relevance scoring based on `config.json` weights.
- **Rule:** Exclude records below `min_relevance_score`.

### Phase IV: Inclusion & Validation
- **Action:** Tagging peer-review status and export.

## 3. Technical Changes

### 3.1. Peer-Review Validation Logic
A new column `Peer_Reviewed` will be added to the CSV/Markdown output based on source metadata:
- **Yes:** Source is `Crossref` (journal-article/proceedings) OR `OpenAlex` (type: journal-article/proceedings).
- **Likely:** Source is `Semantic Scholar` (type: JournalArticle).
- **No / Preprint:** Source is `ArXiv` OR repository versions (Zenodo) without journal links.

### 3.2. Deduplication Engine
Replace DOI-only deduplication with a "Hybrid Slug" approach:
1. Generate `slug = re.sub(r'\W+', '', title.lower())`.
2. Group by `slug`.
3. Select winner based on `Citations` and `Source` hierarchy.

### 3.3. PRISMA Flow Report (`FLUXO_PRISMA.md`)
Generate a markdown file containing:
- **Stats Table:** Raw counts vs. Filtered counts.
- **Mermaid Diagram:** A visual flow of the research funnel.

## 4. Output Data Structure
The exported CSV will include:
- `Title`, `Abstract`, `Peer_Reviewed` (NEW), `Venue` (NEW - Journal/Conf name), `Year`, `URL`, `Source`, `Citations`, `DOI`, `Relevance_Score`.

## 5. Success Criteria
- [ ] No visual duplicates (same title appearing twice).
- [ ] Every entry has a `Peer_Reviewed` status.
- [ ] `FLUXO_PRISMA.md` is generated correctly with a valid Mermaid diagram.
- [ ] Methodology is documented and verifiable through logs.
