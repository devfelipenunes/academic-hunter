# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-06-23

### Added
- **Plugin Architecture**: Modular connector and exporter system with `BaseConnector` and `BaseExporter` ABCs.
- **7 Academic Database Connectors**: ArXiv, Crossref, OpenAlex, Semantic Scholar, CORE, DBLP, DOAJ.
- **5 Export Formats**: CSV, BibTeX, RIS, Markdown Elite Report, PRISMA Flow Report.
- **Multi-Threaded Pipeline**: Concurrent mining with domain-level pacing and rate-limit escalation.
- **DOI-Based Deduplication**: Intelligent merging of duplicate papers across sources.
- **Elite Scoring Engine**: Technical density scoring with title multiplier and citation bonus.
- **Abstract Enrichment**: Automatic DOI-based abstract resolution for papers with missing abstracts.
- **PRISMA Compliance**: Full PRISMA flow report generation with Mermaid diagrams.
- **SQLite Caching**: Thread-safe request cache for reproducible runs.
- **Drex Disambiguation**: Context-aware filtering to avoid false positives (ML vs Fintech).
- **Peer Review Detection**: Heuristic-based detection of peer-reviewed status.
- **Professional Logging**: Structured logging via Python's `logging` module.
- **CI/CD**: GitHub Actions workflow for automated testing.
- **Open-Source Ready**: LICENSE, CONTRIBUTING.md, config.example.json, CHANGELOG.md.

### Changed
- Refactored from monolithic script to modular package (`src/academic_hunter/`).
- `BaseConnector` now provides `_raw_request()` for non-JSON APIs (e.g., ArXiv XML) and `get_headers()` for per-connector API key injection.
- Centralized `_get_run_dir()` in `BaseExporter` (was duplicated in 5 subclasses).
- Removed hardcoded pacing delays — single source of truth via connector class `default_delay` attribute.

## [1.0.0] - 2026-06-17

### Added
- Initial monolithic implementation with ArXiv, Crossref, OpenAlex, and Semantic Scholar.
- Basic keyword search with CSV export.
