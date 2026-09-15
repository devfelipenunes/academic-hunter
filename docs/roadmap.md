# Roadmap de Evolução — Academic Hunter

**Criado em:** 2026-09-10
**Base:** mapeamento arquitetural e de qualidade do código (v2.1.0, 80 arquivos, ~7.000 LOC)

Duas frentes escolhidas: **camada de LLM/agentes** e **retrieval/embeddings**. Este documento
as ordena por dependência — há correções estruturais que precisam vir antes, porque hoje o
sistema não mede o que diz medir.

---

## Fase 0 — Correções que condicionam tudo

> **Status: concluída.** Os cinco itens abaixo foram implementados, mais um sexto que
> não estava previsto aqui: a fusão dos dois sinais foi substituída após a avaliação
> mostrar que a regra vigente ranqueava pior que cada um dos seus próprios componentes
> (`docs/roadmap.md` §2.3 e `evaluation/README.md`). O texto de cada item é
> mantido como registro do problema original — os detalhes de implementação estão nos
> commits e nos docstrings.

Sem isso, qualquer melhoria de retrieval é impossível de avaliar: não dá para saber se um
embedding novo é melhor quando o score reportado não é o score usado.

### 0.1 Unificar a definição de score

**Problema.** `core/pipeline/steps.py:82-85` (`RecomputeRanksStep`) sobrescreve o
`Relevance_Score` de todo paper com a média geométrica de ranks percentis:
`sqrt(rank_sem * rank_kw) * 10`. O score híbrido de `scorer.py:compute_hybrid_score`
(`sqrt(sem)*10 + kw*0.3`) é valor intermediário, descartado antes do filtro
`min_relevance_score`, do export e do PRISMA. Os papers descrevem como score o que o
sistema não reporta como score.

**Ação.** Decidir qual é o score canônico e remover o outro caminho. Se o rank-normalizado
for o correto para ordenação, ele deve ser explicitamente o `Relevance_Score` e o híbrido
deve virar um campo separado (`_hybrid_score`) para diagnóstico. Se o híbrido for o
canônico, `RecomputeRanksStep` não pode sobrescrevê-lo.

**Impacto:** toda comparação experimental e toda métrica futura depende disso.

### 0.2 Corrigir o enricher que reescreve o score

**Problema.** `core/pipeline/enricher.py:73` sobrescreve `Relevance_Score` com o score
keyword bruto **depois** do re-ranking (`manager.py:107` vs `112`), sem renormalizar. Papers
enriquecidos ficam com score em escala diferente dos demais e são filtrados incorretamente.

**Ação:** reordenar (enriquecer antes de recalcular ranks) ou não escrever score no enricher.

### 0.3 Avaliação de retrieval (métrica que hoje não existe)

**Problema.** Não há nDCG, recall@k nem benchmark contra qrels. Um `ndcg_evaluation.json`
incompleto (nDCG = 0, campos ausentes) foi removido por não ter script gerador nem qrels.

**Ação.** Construir um conjunto de avaliação rotulado — mesmo pequeno (50–100 query-paper
pares com juízos de relevância). Só então é possível afirmar que uma mudança de embedding
melhorou o sistema.

**Sem isso, as Fases 1 e 2 ficam sem critério de sucesso.**

### 0.4 Fechar as violações de fronteira

`core/pipeline/steps.py:159` importa `export_to_obsidian` **do adapter MCP** — o domínio
conhece a interface. Além disso, `core` importa plugins concretos em `main.py:48,55`,
`facades.py:165`, `config.py:50`, `manager.py:22`.

**Ação.** Mover as ABCs para `core/` (portas) e inverter as dependências. O export Obsidian
deve virar um passo de pipeline que recebe um exporter injetado.

### 0.5 Higiene de robustez (rápidas)

- `scorer.py:89,94` — `math.sqrt` sem clamp: `ValueError` se o cosseno for negativo.
- `processor.py:19-29` vs `56-60` — TOCTOU no dedup: duas threads podem registrar o mesmo paper.
- `resolvers.py:137` — `track_exclusion` muta estatísticas fora do lock.
- SQLite sem WAL/busy_timeout, apesar do docstring prometer thread-safety.
- `KeywordScreener` (`plugins/screeners/keyword.py:8`) é stub que retorna `1.0` fixo.
- Remover código morto: `decorators.py`, registries `SCREENERS`/`VECTOR_STORES` não consumidos,
  `ConfigHistory.restore` que não restaura.

---

## Fase 1 — Camada de LLM e agentes

Hoje o Academic Hunter é deliberadamente pré-agente: o pipeline não chama LLM nenhum. Isso é
um diferencial (offline, zero custo, reprodutível) e deve ser preservado como modo padrão.
A camada de LLM entra como **opção**, não como dependência.

### 1.1 Triagem assistida por LLM (maior ganho isolado)

O ponto mais fraco do sistema. `KeywordScreener` é stub e o screening semântico é um cosseno
contra centroide. LatteReview e SWARM-SLR fazem triagem com LLM e reportam ganho substancial.

**Desenho:** nova implementação de `BaseScreener` (`plugins/screeners/`) que recebe os
critérios de inclusão em linguagem natural e emite um julgamento estruturado
(`include`/`exclude`/`unsure` + justificativa + confiança). Manter o screener atual como
fallback e comparar os dois na avaliação da Fase 0.3.

**Tecnologias:** structured output / function calling; DSPy para otimizar o prompt de triagem
contra o conjunto rotulado; batching para conter custo.

### 1.2 Extração estruturada de dados

Concorrentes (Elicit, prismAId) extraem campos (população, método, métricas, resultados) para
tabelas comparativas. O AH só exporta metadados.

**Desenho:** nova tool MCP `extract_data` que recebe uma lista de campos e devolve JSON por
paper. Encaixa em `interfaces/mcp/tools/` (auto-registro por assinatura, basta criar o arquivo).

### 1.3 Geração e refinamento de query

Hoje o usuário escreve as âncoras à mão ou usa `quick_topic_discovery` (que só lista títulos).
Há literatura específica: _Adaptive search query generation and refinement in SLR_
(DOI `10.1016/j.is.2023.102231`), já no corpus.

**Desenho:** um ciclo `discovery → config → run → avaliação de recall → refino da query`,
hoje o "Agentic SLR Configuration" prometido nos papers mas não implementado como laço.

### 1.4 O que NÃO fazer

Não tornar o LLM obrigatório. O argumento de venda offline/zero-custo/reprodutível depende
disso, e é o eixo em que o AH ganha de JARVIS, prismAId, Elicit e LatteReview. A regra deve ser:
**LLM é camada opcional, nunca caminho crítico.**

---

## Fase 2 — Retrieval e embeddings

### 2.1 Embeddings de domínio científico

Hoje: `all-MiniLM-L6-v2` (22M parâmetros, treinado em texto genérico).

| Modelo                    | Por quê                                                          | Custo                   |
| ------------------------- | ---------------------------------------------------------------- | ----------------------- |
| **SPECTER2**              | Treinado em citações científicas; é o estado da arte para papers | ~110M, ainda CPU-viável |
| **SciNCL**                | Contrastivo, domínio científico, mais leve que SPECTER2          | ~110M                   |
| **BGE-small / GTE-small** | Já testados em `benchmark_baselines.py`; comparar com MiniLM     | ~33M                    |

**Ação:** rodar `papers/experiments/benchmark_baselines.py` estendido com esses modelos e
medir **na avaliação da Fase 0.3** — não só por correlação de ranking, mas por qualidade de
recuperação.

**Risco:** trocar o modelo muda o comportamento do Weight-Bleeding (os pesos são sobre o
espaço de embedding). Precisa revalidar a §3.7 e a §3.13 do paper de conferência.

### 2.2 Cross-encoder no re-ranking (de verdade)

`rerank_search` existe, mas o cross-encoder só é usado em experimentos — o pipeline usa
bi-encoder. Um cross-encoder em segundo estágio costuma dar o maior ganho por esforço em
retrieval.

**Ação:** adicionar estágio opcional de reranking no pipeline (top-k do bi-encoder → cross-encoder).
O `ms-marco-MiniLM-L-6-v2` já está em cache local.

**Nota:** a §3.13 do paper mostra que o cross-encoder ms-marco mede relevância conversacional,
não temática. Para SLR, um cross-encoder afinado em relevância temática seria mais adequado —
candidato a fine-tuning próprio.

### 2.3 Busca híbrida BM25 + densa

O AH já tem os dois sinais separados (keyword regex + embedding), mas combinados por uma
fórmula fixa. A literatura (Agentic Hybrid Retrieval, arXiv 2604.16394) usa fusão explícita.

**Ação:** implementar Reciprocal Rank Fusion (RRF) como modo alternativo e comparar com o
híbrido atual na avaliação.

### 2.4 Texto completo (a maior lacuna funcional)

Todo o pipeline opera sobre título + abstract. PaperQA2, Scite e JARVIS vão além. É a lacuna
que mais limita o teto de qualidade — abstracts truncam método e resultado.

**Ação:** ingestão de PDF via Unpaywall (a tool já existe) + chunking + indexação no ChromaDB.
Depois, retrieval em nível de chunk em vez de documento.

**Tecnologias:** PyMuPDF para extração; chunking semântico (há paper no corpus:
_Evaluating Chunking Strategies for RAG on Academic Texts_, arXiv 2607.01852).

### 2.5 Conectores inefetivos

O experimento de unicidade (`papers/experiments/source_uniqueness.py`, artefato em
`results/source_uniqueness.json`) mostra que, num corpus de 1.538 papers, **DBLP, DOAJ e CORE
contribuíram zero**. Só quatro fontes trouxeram resultado: OpenAlex 685, Crossref 582, ArXiv
292 e Semantic Scholar 90.

**A explicação anterior estava errada.** Este documento afirmava que os três eram
`is_keyword_only`, e isso não se sustenta no código:

| Conector         | `is_keyword_only` | Contribuiu?         |
| ---------------- | ----------------- | ------------------- |
| DBLP             | **True**          | não                 |
| DOAJ             | **True**          | não                 |
| CORE             | **False**         | não                 |
| Semantic Scholar | **True**          | **sim** (90 papers) |

Ou seja, o flag não separa quem contribui de quem não contribui: CORE é `False` e não trouxe
nada, enquanto Semantic Scholar é `True` e trouxe 90. O flag descreve _como_ o conector é
consultado (por termos genéricos em vez de por categoria técnica), não se o índice dele cobre
o tópico. A causa real da contribuição zero é de cobertura de índice, e é específica do tópico
— não uma propriedade do conector.

**Ação:** medir contribuição marginal em vários tópicos, não em um só, e desativar por padrão
apenas o que não pagar o custo de latência em _todos_ eles. Um único run de blockchain não
autoriza desligar DBLP para sempre — DBLP é forte em ciência da computação e o tópico testado
não era esse.

---

## Fase 3 — Frentes de pesquisa abertas

1. **Ponderação aprendida.** Hoje os pesos são definidos à mão no JSON. Um método que os
   aprenda a partir do conjunto rotulado da Fase 0.3 seria contribuição original — e
   diretamente comparável ao SIF/SGPT.
2. **Grafo de citações.** Snowballing sistemático, PageRank de citações, detecção de frentes
   de pesquisa. JARVIS já tem PageRank; o AH tem apenas contagens isoladas.
3. **Screening colaborativo.** Multi-revisor com resolução de conflito e medida de concordância
   (kappa). Rayyan e Covidence têm; é requisito em revisões Cochrane.
4. **Weight-Bleeding multi-domínio.** A §3.6 mostra que centroides de domínios distintos são
   negativamente correlacionados (ρ = −0.746). Um esquema que compõe múltiplos domínios
   simultaneamente é uma extensão natural do método.

---

## Ordem sugerida

| Ordem | Item                       | Depende de | Por quê primeiro                     |
| ----- | -------------------------- | ---------- | ------------------------------------ |
| 1     | 0.1 score unificado        | —          | Sem isso, nada é mensurável          |
| 2     | 0.3 avaliação rotulada     | 0.1        | Critério de sucesso de tudo depois   |
| 3     | 0.2, 0.4, 0.5              | —          | Baratas, removem ruído               |
| 4     | 2.2 cross-encoder          | 0.3        | Maior ganho por esforço em retrieval |
| 5     | 1.1 triagem por LLM        | 0.3        | Maior lacuna funcional               |
| 6     | 2.1 embeddings científicos | 0.3        | Comparável de forma limpa            |
| 7     | 2.4 texto completo         | 0.3        | Maior teto, maior custo              |
| 8     | 1.2, 1.3, 2.3, 2.5         | —          | Incrementais                         |
| 9     | Fase 3                     | tudo       | Pesquisa                             |

---

## Tecnologias para estudar

| Tecnologia                       | Onde se aplica | Por quê                                                         |
| -------------------------------- | -------------- | --------------------------------------------------------------- |
| **DSPy**                         | 1.1, 1.3       | Otimiza prompts contra métrica, em vez de escrever prompt à mão |
| **SPECTER2 / SciNCL**            | 2.1            | Embeddings treinados em literatura científica                   |
| **Reciprocal Rank Fusion**       | 2.3            | Fusão padrão de rankings heterogêneos                           |
| **PyMuPDF + chunking semântico** | 2.4            | Full-text                                                       |
| **LangGraph**                    | 1.3            | Orquestração do ciclo discovery→config→run (JARVIS usa)         |
| **BERTopic / UMAP / HDBSCAN**    | já usado       | Recalibrar com o novo espaço de embedding                       |
| **Model Context Protocol**       | já usado       | Acompanhar evolução do protocolo                                |
