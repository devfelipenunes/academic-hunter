# Handoff — finalizar o Academic Hunter

Documento de passagem de bastão. **Leia isto primeiro** ao retomar o trabalho numa
sessão nova; os detalhes de cada item estão nos commits e no plano.

Última atualização: **2026-09-10**.

---

## Onde o trabalho está

|              |                                                                                         |
| ------------ | --------------------------------------------------------------------------------------- |
| Branch       | `feat/finalizar-ah` — **15 commits à frente de `main`**, que segue intacta em `ffbbc47` |
| Testes       | **662 passando** (`./venv/bin/python -m pytest tests/ -q`) — mais 2 da flaky do MCP     |
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

Cross-encoder (item 2 abaixo) também fechado: `core/nlp/model_cache.py` cacheia
os modelos que sete call sites recriavam a cada chamada, e
`core/nlp/reranker.py` + `RecomputeRanksStep._apply_rerank` implementam o estágio
opt-in de reranking. Medido — e ele **ganha**, ao contrário do embedding.

Rode `git log --oneline main..feat/finalizar-ah` para a lista.

---

## O que falta

Em ordem de execução sugerida.

### 1. Full-text (Parte 3 do plano) — **núcleo feito**, faltam as tools e a avaliação

As fases A, B e C estão implementadas e commitadas: portas, chunker, adaptadores
(Unpaywall, pypdf, cache) e o `IngestFullTextStep`, tudo opt-in e desligado por
padrão. **Falta a fase D** (as tools MCP `fulltext_status`, `index_fulltext`,
`chunk_search`) **e a fase E** (avaliação na coleção julgada).

Validado ponta a ponta contra as APIs reais. Dois defeitos apareceram ali e em
nenhum teste:

- O adaptador usava só o `best_oa_location`, que o Unpaywall escolhe por
  _confiabilidade_ e que costuma ser a landing page da editora, com
  `url_for_pdf` nulo — enquanto **outro** local do mesmo registro nomeia o PDF.
  Agora prefere o primeiro local que nomeie um PDF, caindo para a landing page só
  quando nenhum nomeia.
- **E a suposição que este documento trazia estava errada.** Ele dizia que "um
  adaptador para PMC (`/pdf/`) recuperaria" os registros sem `url_for_pdf`.
  Medido: `pmc.ncbi.nlm.nih.gov/…/pdf/` responde **200 com HTML** a qualquer
  cliente que não seja navegador, então raspar PDF do PMC não recupera nada. O
  que funciona é o **Europe PMC**, cuja API REST serve os mesmos artigos em
  **JATS XML** — melhor que PDF, porque o XML já vem seccionado, que é
  justamente o que o chunker teria de adivinhar.

  Com ele, o `10.1371/journal.pone.0000308` — antes `download_failed` — passou a
  render 21.979 caracteres e 23 chunks com as seções `abstract`, `introduction`,
  `method`, `results` e `discussion` corretas.

As fontes são encadeadas: Unpaywall primeiro, Europe PMC depois. Um erro de
configuração numa **não** interrompe a outra — elas não compartilham
configuração, e o Europe PMC não usa e-mail — de modo que o full-text funciona
até sem endereço de contato configurado.

O desenho completo está na **Parte 3 do arquivo de plano**. Resumo do que não
pode ser re-derivado:

- **Nada existe hoje**: nenhum download de PDF, extração ou chunking; nenhuma
  dependência de PDF declarada. A tool `find_open_access` devolve só metadados.
- **Portas** em `core/ports/fulltext.py` (`FullTextSourcePort`, `TextExtractorPort`,
  como `Protocol`) e capacidade de chunk como `ChunkStorePort` **separado** em
  `core/ports/vector_store.py` — não tocar em `BaseVectorStore`, para os testes
  existentes seguirem intactos.
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

### 2. Cross-encoder no pipeline (item 2.1 do roadmap) — **FEITO**

Concluído: cache compartilhado de modelos, estágio opt-in de reranking e a
medição. Ver "O que já está feito" e os achados abaixo.

### 3. Ensemble de embeddings (item 2.2)

`papers/experiments/benchmark_baselines.py` já testa MiniLM, BGE-base e GTE-small
— falta o passo de **combinar em vez de comparar**. Medir na coleção julgada.

### 4. Estabilizar os testes de integração do MCP

`tests/interfaces/mcp/test_server_integration.py` é **flaky**: `test_list_tools` e
`test_server_initialize` falham e passam em execuções alternadas, com
`subprocess.TimeoutExpired` após 45 s. Confirmado em cinco execuções. Suíte
instável contradiz "funcionando perfeitamente".

**A causa está medida.** O servidor MCP leva **44,6 s** para responder ao
`initialize` no `main` — medido num worktree limpo do HEAD, sem nenhuma mudança
desta sessão — contra `timeout=45` no teste. O import do módulo custa 1,9 s, logo
o custo está no startup, não no import. Não é falha de protocolo: com o stdin
aberto a tempo, o servidor responde corretamente aos dois pedidos (ids 1 e 2).
É uma corrida contra o relógio, e qualquer variação de carga decide o resultado.
**Portanto: reduzir o startup ou subir o timeout — não mexer no teste**, que está
correto ao exigir resposta.

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

**O cross-encoder ganha onde o embedding perde — e a diferença é grande.**
Medido na coleção julgada (`papers/experiments/rerank_eval.py`, artefato em
`results/rerank_eval.json`), nDCG@10: `bm25` 0,6728 → `rerank@20` **0,7668** →
oráculo do pool inteiro 0,7916. nDCG@5: 0,6459 → 0,8007. MRR: 0,9394 → 1,0000.
Ganha **nos dois tópicos** (+0,1544 e +0,0436), e o top-20 já captura 97% do teto.
Contraste direto com o embedding de bi-encoder, que _reduz_ o nDCG do BM25
monotonicamente com o peso. Os dois sinais são da mesma família "semântica" e
mesmo assim se comportam em direções opostas: só a medição separa.

**O teste do cross-encoder no MCP era vácuo — e o alvo do patch era o motivo.**
`patch("sentence_transformers.cross_encoder.CrossEncoder")` **não** intercepta
`from sentence_transformers import CrossEncoder`; o atributo do pacote continua
ligado à classe real. Verificado isoladamente. O teste carregava o modelo real
(~25 s) e passava de todo modo, porque tanto o caminho de sucesso quanto o
`except` deixam `"Paper A" in result` verdadeiro. O alvo correto é
`sentence_transformers.CrossEncoder`. Vale conferir todo patch de terceiro que
mire um submódulo enquanto o código importa do pacote.

**A flaky do `test_server_integration.py` é uma corrida contra o timeout, e a
causa está medida.** O servidor MCP leva **44,6 s** para responder ao
`initialize` no `main` (medido em worktree limpo, sem nenhuma mudança desta
sessão), contra um `timeout=45` no teste. O import do módulo custa 1,9 s — o
resto é startup. Não é falha de protocolo: com o stdin fechado a tempo, o
servidor responde corretamente (ids 1 e 2). Qualquer variação de carga decide o
resultado. A correção é reduzir o startup ou subir o timeout, não mexer no teste.

**`Relevance_Score` é arredondado a 1 casa, e isso invalida o reranking
ingênuo.** `steps.py` escreve `round(score, 1)` numa escala 0–10 e todo o
downstream ordena pelo valor **arredondado**. Devolver as notas dos candidatos
na ordem nova preserva o multiconjunto e perde a ordem: duas notas 7,24 e 7,21
colidem em 7,2 e o `sorted` estável volta à ordem de inserção. O ranqueamento
base já produz só 14–19 valores distintos num top-20. A regra que funciona
constrói a ordem na resolução de exportação (`rerank_scores`). Há teste
específico que falha na regra ingênua.

**A `score_precision` era ignorada ali — corrigido.** O `steps.py` arredondava
`Relevance_Score` para 1 casa fixo, embora a setting exista e seja respeitada em
`core/nlp/scorer.py` e nos validators. O rerank tornou a divergência
_load-bearing_: `rerank_scores` constrói a rede **na** precisão em que o score é
escrito, e uma rede mais fina que o arredondamento seria apagada levando a ordem
junto. Agora um único `_score_decimals` alimenta os dois.

**Uma revisão de qualidade pegou duas coisas que a medição não pegaria.** Vale
registrar porque são da mesma família — código que afirma uma coisa e faz outra:

- O script de medição gravava `remap_rule: "... see reranker.rerank_scores"` no
  artefato **sem nunca chamar `rerank_scores`**; fazia um `sorted(head) + tail`
  próprio. Os números por acaso coincidiam (a regra redistribui os scores
  preservando a ordem do cross-encoder), mas a proveniência apontava para código
  não exercitado. Ao consertar, o `Timing` do projeto se revelou a abstração
  certa — a docstring dele já dizia contar pares `(query, documento)`, e eu havia
  escrito o contrário para justificar não usá-lo.
- `settings.rerank.enabled` usava `bool(...)`, e **`bool("false")` é `True`** — um
  `"enabled": "false"` escrito como string ligava o estágio. Agora só um booleano
  real habilita.
- E o estágio contava como reranqueado o que não foi: quando a faixa de scores é
  estreita demais para a rede, `rerank_scores` abstém e devolve tudo intacto, mas
  `stats["reranked"]` e os diagnósticos já tinham sido gravados. Agora o contador
  conta o que **mudou** e os diagnósticos registram o que o cross-encoder **disse**
  — dois fatos distintos, ambos verdadeiros.

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
| Reranking           | Opt-in por `settings.rerank`, **desligado por padrão**            |
| Reranking sem query | Não atua: o cross-encoder pontua o par (query, documento)         |

---

## Pendências que dependem do autor do projeto

1. **Revisar os 598 julgamentos** da coleção. São meus, por leitura de título e
   abstract, de anotador único, sem medida de concordância. As conclusões só valem
   na medida em que as etiquetas valem, e o README da avaliação registra isso.
2. **Rotacionar a chave do Semantic Scholar.** A chave vazada no histórico do git
   continua comprometida: os `refs/pull/*` do GitHub não são removíveis por push.
3. **Revisar os papers** — adiado por decisão. A Tabela 2 do paper de conferência
   e o parágrafo de ablation do JOSS precisam de atenção (ver achados acima).
4. **Decidir se liga o reranking.** A medição recomenda: ganha nos dois tópicos,
   +0,0940 de nDCG@10 no top-20. O default do _produto_ continua `false` porque
   `sentence-transformers` é o extra opcional `ml` (~2 GB) e um default ligado
   faria a instalação mínima falhar em silêncio. Ligar é uma linha no
   `config.json` local: `"rerank": {"enabled": true}`, junto de um
   `ranking_query` — sem query o estágio avisa e não atua.
