# Handoff — finalizar o Academic Hunter

Documento de passagem de bastão. **Leia isto primeiro** ao retomar o trabalho numa
sessão nova; os detalhes de cada item estão nos commits e no plano.

Última atualização: **2026-09-10**.

---

## Onde o trabalho está

|              |                                                                                         |
| ------------ | --------------------------------------------------------------------------------------- |
| Branch       | `feat/finalizar-ah` — **15 commits à frente de `main`**, que segue intacta em `ffbbc47` |
| Testes       | **628 passando** (`./venv/bin/python -m pytest tests/ -q`)                              |
| Working tree | limpo                                                                                   |
| Plano        | `/l/disk0/fnunes/.claude/plans/cozy-purring-hejlsberg.md`                               |

O objetivo acordado é **deixar a aplicação completa e funcionando perfeitamente**,
antes de voltar aos papers. LLM/SLM **só como experimento**, nunca no pipeline.
Fase 3 do roadmap (frentes de pesquisa) está fora do escopo.

### Comandos deste ambiente

- Python do projeto: `./venv/bin/python` — **`python` não existe** neste shell.
- Suíte: `./venv/bin/python -m pytest tests/ -q` (~3 min).
- Arquitetura: `./venv/bin/python -m pytest tests/test_architecture.py -q` —
  reprova qualquer import de `core/` para `interfaces/`, `app/` ou `plugins/`.

---

## O que já está feito

Fase 0 do roadmap fechada (0.1 score unificado, 0.2 enricher, 0.3 avaliação
rotulada, 0.4 fronteiras hexagonais, 0.5 robustez), mais a camada de escrita,
a correção da fusão do score, a coleção julgada em dois tópicos, métricas de
custo, cache de embedding e o ranking por consulta com BM25.

Rode `git log --oneline main..feat/finalizar-ah` para a lista.

---

## O que falta

Em ordem de execução sugerida.

### 1. Full-text (Parte 3 do plano) — o maior bloco, não começou

O desenho completo está na **Parte 3 do arquivo de plano**. Resumo do que não
pode ser re-derivado:

- **Nada existe hoje**: nenhum download de PDF, extração ou chunking; nenhuma
  dependência de PDF declarada. A tool `find_open_access` devolve só metadados.
- **Portas** em `core/ports/fulltext.py` (`FullTextSourcePort`, `TextExtractorPort`,
  como `Protocol`) e capacidade de chunk como `ChunkStorePort` **separado** em
  `core/ports/vector_store.py` — não tocar em `BaseVectorStore`, para os 628
  testes existentes seguirem intactos.
- **`core/fulltext/chunker.py`** puro. Tamanho do chunk: **180 palavras com 40 de
  sobreposição**. Não é ajuste — o embedding padrão do ChromaDB é o MiniLM ONNX,
  com limite de 256 word-pieces (~190 palavras); chunk maior fica parcialmente
  invisível para o retriever, em silêncio. Nunca atravessar fronteira de seção;
  excluir `references` e `appendix` por padrão.
- **`pypdf`, não PyMuPDF.** O roadmap nomeia PyMuPDF, mas ele é **AGPL-3.0** e o
  projeto é MIT. `pypdf` é BSD-3 e vira o extra `fulltext`.
- **Coleção separada `paper_chunks`**, não um campo `doc_type` na `papers`: o
  ChromaDB não tem operador `$exists`, e todo documento legado não tem essa
  chave — um filtro por ela esvaziaria o `semantic_search` de todo o acervo.
- **`IngestFullTextStep` opt-in** (`settings.fulltext.enabled`, default `false`),
  rodando **depois do filtro de limiar**, para gastar download só nos ~270
  incluídos. **Nunca levanta.** Registrar o status por paper (`unavailable`,
  `download_failed`, `no_text_layer`) porque metodologia de SLR exige reportar
  quantos full texts não foram obtidos.
- **Armadilha da avaliação**: o qrels é autocontido e **não tem PDFs**. Medir
  retrieval por chunk exige resolver N PDFs em OA, e a maioria pode não resolver
  — o que mediria o conjunto de candidatos, não o retriever. Commitar um
  `fulltext_coverage.json` e comparar só no subconjunto com respaldo de chunk.

### 2. Cross-encoder no pipeline (item 2.1 do roadmap)

O modelo `cross-encoder/ms-marco-MiniLM-L-6-v2` **já está em cache local** e é
usado em `interfaces/mcp/tools/rag.py` — mas **instanciado a cada chamada**, sem
cache do objeto. Primeiro passo barato: singleton. Segundo: estágio opcional de
reranking no pipeline, opt-in.

### 3. Ensemble de embeddings (item 2.2)

`papers/experiments/benchmark_baselines.py` já testa MiniLM, BGE-base e GTE-small
— falta o passo de **combinar em vez de comparar**. Medir na coleção julgada.

### 4. Estabilizar os testes de integração do MCP

`tests/interfaces/mcp/test_server_integration.py` é **flaky**: `test_list_tools` e
`test_server_initialize` falham e passam em execuções alternadas, com
`subprocess.TimeoutExpired` após 45 s. Confirmado em cinco execuções. Suíte
instável contradiz "funcionando perfeitamente".

### 5. Tag de release

Decisão tomada: **3.0.0**. As mudanças incluem remoção do entry point
`academic-hunter` e movimentação de `core/engine/` para `app/`, o que sob SemVer
pede major. `CITATION.cff` já está no lugar, com a versão casada em `__version__`
(hoje `2.1.0`) — **suba os dois juntos** ou eles divergem.

### 6. Conectores (item 2.4)

Medir contribuição marginal por fonte em vários tópicos e desativar por padrão as
que não pagam o custo. Ver a correção do diagnóstico no `docs/roadmap.md` §2.5:
o flag `is_keyword_only` **não** separa quem contribui de quem não contribui.

---

## Achados que não podem ser re-descobertos

Custaram caro e estão registrados aqui para não se repetirem.

**BM25 supera todo o aparato semântico.** Medido na coleção julgada (108
documentos, 11 consultas, nDCG@10): `bm25` **0,6728** · `keyword` 0,3364 ·
`weighted_norm` 0,3223 · `rank_geometric` 0,2012 · `embedding` 0,1991. E o
embedding custa **~1,5 s por documento** contra 0,006 ms do BM25. Somar o
embedding ao BM25 **piora** monotonicamente com o peso.

**A fusão por ranks percentis destruía informação.** A regra antiga media pior que
cada um dos seus próprios componentes. Substituída por soma ponderada de scores
min-max normalizados.

**A ablation de três modos deixou de medir os modos.** O modo atua no ingest; o
`Relevance_Score` reportado vem de uma fusão independente do modo. `Final` e os
top-scores são iguais por construção — a Tabela 2 do paper de conferência e o
parágrafo de ablation do JOSS estão medindo variação de fonte entre execuções.

**Nunca selecionar o pool de avaliação pela métrica sob teste.** Restringe a
amplitude da variável e a faz parecer pior. A primeira versão do pool usava só o
top-30 por score e o baseline de citações "venceu". Há teste de regressão.

**`Paper.__init__` copia apenas as 14 chaves de `FIELD_SCHEMA`** — passar campos
com `_` ao construtor os descarta em silêncio. Atribuir depois da construção.

**Verificar todo teste de regressão contra o código antigo.** Três testes escritos
nesta sessão passavam no código defeituoso e precisaram ser reescritos. Um teste
que não falha no bug não é teste de regressão.

**`config.json` é reescrito pelo `run_ablation.py`** (precisa, para fixar o modo).
O `save()` escreve as 7 chaves que o arquivo tem, então não há perda, mas rodar a
ablation mexe na config viva.

**`pgrep -f <padrão>` casa com o próprio shell que espera.** Um loop
`until ! pgrep -f run_ablation` nunca termina, porque a linha de comando do shell
contém o padrão.

---

## Decisões já tomadas (não reabrir sem motivo)

| Decisão             | Escolha                                                           |
| ------------------- | ----------------------------------------------------------------- |
| CLI                 | Removido; o MCP é a única interface                               |
| LLM/SLM             | Só como experimento, nunca no pipeline                            |
| Fase 3 (pesquisa)   | Fora do escopo                                                    |
| Anotação da coleção | Eu rotulo, o autor do projeto revisa — **revisão ainda pendente** |
| Versão da release   | 3.0.0                                                             |
| Biblioteca de PDF   | `pypdf` (o PyMuPDF do roadmap é AGPL)                             |

---

## Pendências que dependem do autor do projeto

1. **Revisar os 598 julgamentos** da coleção. São meus, por leitura de título e
   abstract, de anotador único, sem medida de concordância. As conclusões só valem
   na medida em que as etiquetas valem, e o README da avaliação registra isso.
2. **Rotacionar a chave do Semantic Scholar.** A chave vazada no histórico do git
   continua comprometida: os `refs/pull/*` do GitHub não são removíveis por push.
3. **Revisar os papers** — adiado por decisão. A Tabela 2 do paper de conferência
   e o parágrafo de ablation do JOSS precisam de atenção (ver achados acima).
