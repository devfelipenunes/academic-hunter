# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.1.0] - 2026-09-10

### Added

- **Full-text: download, extração e retrieval por trecho.** Até aqui todo o
  pipeline operava sobre título + abstract, que trunca método e resultado — a
  maior lacuna funcional do projeto. Agora `settings.fulltext.enabled` (default
  **`false`**) liga um passo que, para os papers que passaram do limiar, resolve
  a versão em acesso aberto no Unpaywall, baixa o PDF, extrai o texto com
  `pypdf` (extra opcional `fulltext`), fatia em chunks e indexa numa coleção
  separada `paper_chunks`.
  - **Chunk de 180 palavras com 40 de sobreposição, e o número não é ajustável
    por gosto:** o MiniLM do ChromaDB trunca em 256 word-pieces (~190 palavras),
    então um chunk maior ficaria parcialmente invisível para o retriever sem
    nada reportar. Nunca atravessa fronteira de seção, e `references`/`appendix`
    ficam de fora.
  - **Coleção separada, não um campo `doc_type`:** o ChromaDB não tem `$exists`,
    e nenhum documento indexado por runs anteriores tem essa chave — filtrar por
    ela esvaziaria o `semantic_search` de todo o acervo legado.
  - **Status por paper** (`_full_text_status`), com agregados no `stats` e no
    PRISMA: metodologia de SLR exige reportar quantos full texts não foram
    obtidos, e "não há cópia em acesso aberto" é um achado diferente de "o
    download falhou".
  - **O passo nunca levanta** e é sequencial, com orçamento de papers e de tempo.
    PDFs ficam em `.academic_hunter/fulltext/`, o que torna a segunda execução
    offline.
  - **Duas fontes encadeadas.** Unpaywall primeiro — é o índice de onde vivem as
    cópias abertas — e **Europe PMC** depois. O segundo entrou por medição: o
    Unpaywall com frequência sabe que um artigo é aberto sem nomear PDF, e o
    PMC _web_ responde 200 com HTML a qualquer cliente que não seja navegador,
    então raspar `/pdf/` de lá não recupera nada. A API REST do Europe PMC serve
    os mesmos artigos em **JATS XML** — e o XML já vem seccionado, que é o que o
    chunker teria de adivinhar. Um erro de configuração numa fonte não
    interrompe a outra: o Europe PMC não usa e-mail, então o full-text funciona
    até sem endereço de contato.
  - `pypdf` e não PyMuPDF: o segundo é AGPL-3.0 e o projeto é MIT.
  - **Três tools MCP**: `fulltext_status` (quanto full text o corpus tem, com a
    proveniência de cada número), `index_fulltext` (indexa sob demanda, sem exigir
    que o passo esteja ligado na config) e `chunk_search` (trechos agrupados sob o
    paper de origem, com seção e offsets).
  - **Sem número de página, de propósito.** O PDF tem páginas; o JATS do Europe
    PMC não tem. O campo existiria para metade dos papers e faltaria para a
    outra, o que é pior que não ter — a tool devolve seção, índice do chunk e
    offsets de caractere no texto extraído, que é o que existe de fato.
  - **O chunk guarda a identidade do paper** (`title`/`doi`/`year`/`source`) na
    metadata, para o `chunk_search` nomear a origem sem depender do CSV do
    último run — que não é versionado e é limpo.
  - **`already_indexed`**: um paper cujos chunks já estão no índice não é baixado
    nem re-embeddado. O status é contado à parte no PRISMA, porque "já estava
    indexado" não é "não foi obtido".
  - **Agradecimentos ficam de fora, como `references` e `appendix`.** Medido num
    paper real: uma consulta sobre o próprio assunto do artigo devolveu a seção
    de agradecimentos em **dois dos três primeiros lugares** — lista de autores,
    financiadores e conflito de interesses, que casa com qualquer consulta sobre
    pessoas e não responde nenhuma. (`funding` é a mesma seção.)
  - **`no_sections` é um status próprio**, separado de `no_text_layer`: aquele
    significa PDF escaneado e aponta para OCR; este significa texto extraído sem
    seção reconhecível e aponta para o extrator — consertos diferentes.
  - **Falha de download guarda o motivo** (`_full_text_error` por paper).
    `download_failed` cobre três situações distintas — erro transitório, cópia
    aberta que é só uma landing page, e editora recusando cliente que não seja
    navegador — e só a primeira vale retentar. Medido: uma segunda passada
    recuperou um documento que havia falhado na primeira.

- **Fronteiras hexagonais explícitas**: `core/ports/` passa a declarar os contratos
  (`BaseExporter`/`ExportContext`, `BaseScreener`, `BaseVectorStore`, `ConnectorPort`), e a
  camada `app/` concentra a composição. `core` não importa mais `plugins`, `interfaces` nem
  `app` — verificado por `tests/test_architecture.py`, que reprova a regressão.
- **Avaliação de retrieval** (`core/evaluation/`): nDCG@k, recall@k, precision@k, MRR, MAP,
  formato de coleção julgada (_qrels_) com validação estrita, e um runner que reporta a
  cobertura julgada para que uma métrica que mede o qrels, e não o retriever, apareça como
  tal. Acompanha uma coleção julgada de 108 documentos em dois tópicos, em `papers/evaluation/`.
- **Camada de escrita** (`core/writing/`): templates de artigo, convenções de estilo, geração
  determinística de outline e verificadores de citação e de número. Exposta por quatro tools
  MCP (`outline_paper`, `paper_context`, `verify_citations`, `verify_numbers`).
- **Injeção de dependências** no `AcademicHunter`: `exporters`, `vector_store_factory`,
  `obsidian_export` e `semantic_screener` passam a ser injetáveis.
- `CITATION.cff`.
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
- **Cache compartilhado de modelos** (`core/nlp/model_cache.py`): os sete call
  sites que construíam o próprio modelo a cada chamada — `summarize`, `dedup`,
  `clustering`, `novelty`, `visualization` (duas vezes) e o `CrossEncoder` do
  `rag.py` — passam a compartilhar uma instância por processo. Carregar o
  cross-encoder custa **5,9 s** em CPU, e era pago em toda invocação antes de
  qualquer trabalho. O import de `sentence-transformers` continua lazy (extra
  `ml` opcional) e uma falha de carga **não** é cacheada, para instalar o extra
  passar a funcionar sem reiniciar o servidor.
- **Reranking por cross-encoder, opt-in** (`settings.rerank`): estágio de
  segundo nível sobre o topo do ranking, dentro do `RecomputeRanksStep` para que
  `Relevance_Score` siga com um único escritor. Desligado por padrão. Medido na
  coleção julgada (nDCG@10, 108 documentos, 11 consultas): `bm25` 0,6728 →
  `rerank@20` **0,7668** → oráculo do pool inteiro 0,7916; nDCG@5 0,6459 →
  0,8007; MRR 0,9394 → 1,0000. Ganha **nos dois tópicos** (+0,1544 e +0,0436), e
  o top-20 já captura 97% do teto. É o oposto do embedding — que _piora_ o BM25
  monotonicamente — e a diferença só apareceu por medir. Script e artefato:
  `papers/experiments/rerank_eval.py` → `results/rerank_eval.json`.
- `settings.rerank` documentado em `config.example.json` (`enabled`, `model`,
  `top_n`, `max_length`). Exige `settings.ranking_query`: sem consulta não há par
  (query, documento) para o cross-encoder ler, e o estágio avisa e não atua.

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

- `settings.score_precision` era ignorada no `RecomputeRanksStep`, que arredondava
  `Relevance_Score` para 1 casa fixo. Passa a ser lida (com fallback), e a mesma precisão
  alimenta a rede do reranking — que tem de ser construída na resolução em que o score é
  escrito, senão o arredondamento apaga a ordem que o reranking produziu.
- `settings.rerank.enabled` aceitava qualquer valor _truthy_: `"enabled": "false"`, escrito
  como string no JSON, **ligava** o estágio e seus ~6 s de carregamento de modelo. Agora só
  um booleano real habilita.
- O reranking reportava um trabalho que não aconteceu: quando a faixa de scores dos candidatos
  é estreita demais para a rede, `rerank_scores` abstém e devolve tudo intacto, mas o estágio
  já gravava `_rerank_score`/`_rerank_rank` e contava os papers como reranqueados. Agora
  `stats["reranked"]` conta só o que **mudou de fato**, e o log distingue os dois casos.
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
- **Só o 429 tinha espera entre tentativas.** Um 5xx ou uma conexão derrubada voltavam na hora:
  o orçamento de retry era gasto no mesmo instante em que o servidor disse "agora não", o que
  não é retentar, é a mesma requisição duas vezes. Agora 5xx e erro de rede esperam, dobrando a
  cada tentativa, e nada é esperado depois da última.
- **`blocked_sources` nunca era limpo entre runs.** O conjunto vive na config, que sobrevive ao
  run: um 429 pedindo espera longa silenciava aquela fonte em toda execução seguinte do mesmo
  processo, sem volta a não ser reiniciar. O bloqueio passa a ser propriedade do run.
- **Escrita sem escape nos exportadores.** Um `}` no título fechava o campo BibTeX antes do fim
  e o resto do registro virava lixo — só o abstract era escapado. No RIS, um `\n` num campo
  quebrava a linha e criava um tag que o leitor não reconhece. No frontmatter do Obsidian, uma
  aspa no tópico custava a nota inteira o frontmatter, que é o que a torna encontrável.
- **`run_stats_*.json` era escrito direto no caminho final.** Qualquer leitor que caísse na
  janela de escrita abria um arquivo pela metade e recebia erro de parse de um arquivo que está
  íntegro um milissegundo depois. Passa a gravar num temporário irmão e renomear.
- **O cache engolia a exceção de leitura sem log**, enquanto a de escrita registrava. Uma
  resposta `None` para tudo transforma cada run em run de rede, e o sintoma é lentidão — nada
  aponta para o arquivo. O teste que cobria isso era **vacuoso**: corrompia só o arquivo
  principal, e o SQLite recuperava o banco pelo `-wal`, então o `except` nunca era alcançado.
- **Semantic Scholar era registrado como `"Semantic Scholar"` e carimbava
  `"SemanticScholar"`**, então o run reportava essa fonte com uma contagem e uma segunda fonte
  com zero. O nome passa a ser declarado uma vez por conector (`SOURCE_NAME`) e o registro
  recusa carregar um conector cujo nome divirja do que ele carimba.

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
