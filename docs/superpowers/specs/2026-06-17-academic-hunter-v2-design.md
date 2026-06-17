# Design Spec: Academic Hunter V2 - High Coverage Edition (Updated Weights)

**Date:** 2026-06-17
**Author:** Gemini CLI
**Status:** Approved by User

## 1. Goal
Transform `academic_hunter.py` into a high-coverage, systematic literature review engine focused 100% on academic papers, with a sophisticated scoring system driven by `config.json`.

## 2. Core Architecture
- **Multi-Source Aggregation:** Integration with ArXiv, Semantic Scholar, Crossref, and **OpenAlex**.
- **Exhaustive Query Logic:** Every anchor-string combination will be queried. Support for boolean group searches.
- **Deduplication Engine:** DOI-based merging of records from different sources.
- **Config-Driven Scoring:** All weights moved to `config.json`. No hardcoded values in Python.

## 3. Scoring System 2.0 (Elite Technical)
Weights are categorized to reflect innovation and strategic value:
- **Critical (5.0):** Atomic settlement, ISO 20022, ZKP, Shared ledger, CBDC.
- **Strategic (3.0):** Cross-border payments, Consensus, RTGS, Interoperability, Trust models.
- **Architectural (2.0):** Modular architecture, Event logs, VMs, Payment APIs.
- **Methodological (1.5):** Comparative analysis, Surveys, Taxonomy, Scalability.

**Logic Enhancement:**
- Terms found in the **Title** receive a **1.5x multiplier** over their base weight.

## 4. Implementation Steps (Overview)
1. **Update `config.json`:** Add `settings` and `pesos_tecnicos` sections.
2. **Refactor `AcademicHunter` Class:**
    - Update `__init__` to load new config sections.
    - Implement OpenAlex connector.
    - Revamp `calculate_score` for title-bonus and config-weights.
    - Fix Semantic Scholar search logic.
3. **Enhance Pipeline:**
    - Implement DOI-based deduplication.
    - Improve CSV export and add Markdown summary report.

## 5. Success Criteria
- [ ] Comprehensive coverage of all `config.json` terms.
- [ ] DOI-verified deduplication.
- [ ] Scoring accuracy validated against the new weight table.
- [ ] Export of a "Master Report" (MD) and a "Clean Dataset" (CSV).
