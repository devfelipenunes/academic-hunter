# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Fronteiras hexagonais explícitas**: `core/ports/` passa a declarar os contratos
  (`BaseExporter`/`ExportContext`, `BaseScreener`, `BaseVectorStore`, `ConnectorPort`), e a
  camada `app/` concentra a composição. `core` não importa mais `plugins`, `interfaces` nem
  `app` — verificado por `tests/test_architecture.py`, que reprova a regressão.
- **Avaliação de retrieval** (`core/evaluation/`): nDCG@k, recall@k, precision@k, MRR, MAP,
  formato de coleção julgada (_qrels_) com validação estrita, e um runner que reporta a
  cobertura julgada para que uma métrica que mede o qrels, e não o retriever, apareça como
  tal. Acompanha uma coleção piloto de 58 documentos avaliados em `papers/evaluation/`.
- **Camada de escrita** (`core/writing/`): templates de artigo, convenções de estilo, geração
  determinística de outline e verificadores de citação e de número. Exposta por quatro tools
  MCP (`outline_paper`, `paper_context`, `verify_citations`, `verify_numbers`).
- **Injeção de dependências** no `AcademicHunter`: `exporters`, `vector_store_factory`,
  `obsidian_export` e `semantic_screener` passam a ser injetáveis.
- `CITATION.cff`.

### Added
- **BM25** (`core/nlp/bm25.py`) e **ranking por consulta**: definir
  `settings.ranking_query` troca o sinal esparso da contagem de termos do domínio
  por BM25 sobre essa consulta. É o primeiro sinal do pipeline condicionado à
  consulta — a contagem de termos responde "este paper parece com o domínio?" e
  nunca vê uma pergunta. Medido na coleção julgada, **ter uma consulta** levou o
  nDCG@10 de 0,28 para 0,67, mais do que qualquer mudança de regra de
  pontuação conseguiu.
- **Métricas de custo** na avaliação (`Timing`, `build_rankings_timed`): tempo
  total, por documento e por consulta, ao lado das métricas de qualidade.
- Cache LRU do embedding do paper no `SemanticScreener`. O mesmo texto era
  re-embedado a cada chamada, e o pipeline pontua o mesmo paper mais de uma vez
  — cerca de 1,5 s por documento com abstract. Medido: 1500 ms → 209 ms.

### Changed

- **Fusão do score substituída.** A regra vigente (`sqrt(rank_kw × rank_sem) × 10`) media
  _pior que cada um dos seus próprios componentes_: converter os dois sinais em ranks
  percentis antes de combinar descarta a magnitude. Agora é soma ponderada de scores min-max
  normalizados, 70% keyword / 30% embedding. A regra antiga continua disponível em
  `settings.fusion = "rank_geometric"` para reproduzir execuções anteriores.
- **Dois scores com nomes distintos.** `_hybrid_score` é o score de inclusão (dependente do
  modo de ablation, escrito no ingest); `Relevance_Score` é o reportado, com um único
  escritor. Novo limiar `min_inclusion_score`, para uma constante parar de significar duas
  coisas em escalas diferentes.
- **O CLI interativo foi removido.** O projeto é um servidor MCP; o entry point `academic-hunter`
  sai do `pyproject.toml`. Use `academic-mcp`.

### Fixed

- `RecomputeRanksStep` fazia _early return_ com menos de dois papers, deixando `Relevance_Score`
  no valor padrão — o filtro de limiar então descartava tudo em silêncio, esvaziando qualquer
  run que deduplicasse para um único paper.
- `included_final` era inflado: o duplicado já mesclado era contado junto com o paper em que
  se fundiu, produzindo estatísticas maiores que o número de papers existentes.
- O enricher sobrescrevia `Relevance_Score` com score keyword bruto depois do re-ranking,
  colocando duas escalas na mesma coleção enquanto ambas eram comparadas ao mesmo limiar.
- `math.sqrt` sem clamp no scorer: cosseno é assinado, e um par anti-correlacionado levantava
  `ValueError`, abortando o run.
- TOCTOU no dedup: a checagem e o registro dos identificadores estavam em duas aquisições de
  lock separadas, permitindo que duas threads registrassem o mesmo paper.
- `track_exclusion` mutava estatísticas fora do lock.
- SQLite passa a abrir com WAL e `busy_timeout` — sem isso o `SQLiteCache` não era thread-safe
  apesar do docstring afirmar que era.

### Removed

- `interfaces/mcp/decorators.py` (zero consumidores fora do próprio teste; o servidor registra
  tools por assinatura), `KeywordScreener` (stub que retornava `1.0` fixo e nunca era
  instanciado), os registries `SCREENERS`/`VECTOR_STORES` (nunca consultados) e
  `ConfigHistory.restore` (retornava `True` sem restaurar nada).

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
