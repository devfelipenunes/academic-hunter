# Mapeamento de Ferramentas: Panorama Comparativo do Academic Hunter

**Status:** documento de trabalho — base para o artigo de mapeamento
**Última revisão:** 2026-09-10

---

## 1. Propósito e método

Este documento consolida, num único lugar, o levantamento de ferramentas relacionadas ao
Academic Hunter. Antes, esse mapeamento estava espalhado em três lugares com granularidades
diferentes (`papers/novelty-analysis.md` §2.2/§3/§8, Related Work do JOSS, Related Work do
paper de conferência), o que tornava impossível auditar a cobertura ou verificar quando cada
ferramenta foi checada pela última vez.

### 1.1 Como o levantamento foi feito

As ferramentas foram identificadas por quatro vias complementares:

1. **Busca no corpus indexado do próprio Academic Hunter** (`semantic_search`,
   `quick_topic_discovery`, `find_related_papers`) — 10.500 papers no vector store local.
   O Academic Hunter foi usado para mapear o próprio campo em que se insere.
2. **Literatura cinzenta e web** — documentação de produto, repositórios e comparativos
   publicados de terceiros.
3. **Referências cruzadas** — cadeias de citação a partir das ferramentas já conhecidas.
4. **Catálogos de MCP servers** — npm, PyPI e listas comunitárias.

### 1.2 Critérios de inclusão

Uma ferramenta entra no mapeamento se satisfizer **ao menos um** dos critérios:

- Executa alguma etapa do fluxo de revisão sistemática (busca, triagem, extração, síntese);
- Expõe retrieval acadêmico como ferramenta para agentes de IA;
- Propõe um método de ponderação semântica em embeddings (mesmo sem ser ferramenta SLR).

### 1.3 Critérios de exclusão

- Bases de dados puras sem camada de software (Scopus, Web of Science) — são fontes, não ferramentas;
- Bibliotecas genéricas de RAG (LangChain, LlamaIndex) sem especialização acadêmica;
- Projetos sem código, documentação ou publicação verificável.

### 1.4 Limitações declaradas

- **Não houve revisão sistemática formal com protocolo registrado.** É um mapeamento
  exploratório; a §1.1 descreve as vias usadas, não um protocolo PRISMA.
- **Ferramentas comerciais são avaliadas por documentação pública**, não por teste direto —
  não foi possível executar Elicit, Consensus, Scite, Undermind ou SciSpace nas mesmas condições.
- **Datas de verificação** estão na coluna "Verificado em" da tabela da §3. O campo de
  software se move rápido; qualquer afirmação sobre concorrentes deve ser reconferida antes
  da submissão.

---

## 2. Taxonomia

As ferramentas se distribuem em cinco categorias, por **estágio do fluxo** e **modelo de entrega**:

| Categoria                          | O que é                                                           | Exemplos                                           |
| ---------------------------------- | ----------------------------------------------------------------- | -------------------------------------------------- |
| **A. Triagem e síntese**           | Ferramentas de screening/evidence synthesis, majoritariamente web | ASReview, Rayyan, Covidence                        |
| **B. Descoberta assistida por IA** | Busca e leitura de literatura mediada por LLM                     | Elicit, Consensus, Scite, Undermind, SciSpace      |
| **C. Métodos de ponderação**       | Contribuições metodológicas sobre embeddings                      | SIF, SGPT, Echo, LLM2Vec, GRIT, Weight-Bleeding    |
| **D. MCP servers acadêmicos**      | Retrieval acadêmico exposto como ferramenta a agentes             | lit-review-mcp, academic-search-mcp, citecheck     |
| **E. SLR com IA generativa**       | Pipelines completos de SLR dirigidos por LLM                      | JARVIS, LatteReview, SWARM-SLR, EmbedSLR, PaperQA2 |

**Nota sobre fronteiras:** as categorias se sobrepõem. O Academic Hunter é o único item que
aparece simultaneamente em A (tem triagem), C (propõe um método), D (é MCP server) e E
(executa pipeline completo) — sem depender de LLM. Essa sobreposição é o argumento central
do posicionamento e está detalhada na §5.

---

## 3. Inventário com status de verificação

| Ferramenta                  | Categoria  | Licença / Custo            | Verificado em | Status                               |
| --------------------------- | ---------- | -------------------------- | ------------- | ------------------------------------ |
| **Academic Hunter**         | A, C, D, E | MIT / zero                 | 2026-09-10    | Ativo                                |
| ASReview                    | A          | Apache / zero              | 2026-09-10    | Ativo                                |
| Rayyan                      | A          | Freemium                   | 2026-09-10    | Ativo                                |
| Covidence                   | A          | Pago (institucional)       | 2026-09-10    | Ativo                                |
| EPPI-Reviewer               | A          | Pago                       | 2026-09-10    | Ativo                                |
| Abstrackr                   | A          | Zero                       | 2026-09-10    | Legado                               |
| Colandr                     | A          | MIT                        | 2026-09-10    | Legado                               |
| RevMan                      | A          | Zero (Cochrane)            | 2026-09-10    | Ativo                                |
| Elicit                      | B          | Freemium (~US$14/mês)      | 2026-09-10    | Ativo                                |
| Consensus                   | B          | Freemium (~US$12/mês)      | 2026-09-10    | Ativo                                |
| Scite                       | B          | Pago (~US$12–20/mês)       | 2026-09-10    | Ativo                                |
| Undermind                   | B          | Freemium (~US$19/mês)      | 2026-09-10    | Ativo                                |
| Ai2 Paper Finder            | B          | Zero (Ai2)                 | 2026-09-10    | Ativo                                |
| SciSpace                    | B          | Freemium (~US$12–90/mês)   | 2026-09-10    | Ativo                                |
| ResearchRabbit              | B          | Zero                       | 2026-09-10    | Ativo                                |
| Litmaps                     | B          | Freemium                   | 2026-09-10    | Ativo                                |
| Connected Papers            | B          | Freemium                   | 2026-09-10    | Ativo (desenvolvimento desacelerado) |
| SIF                         | C          | Método (ICLR 2017)         | 2026-09-10    | Referência                           |
| SGPT                        | C          | Método (EMNLP 2022)        | 2026-09-10    | Referência                           |
| Echo embeddings             | C          | Método (ICLR 2025)         | 2026-09-10    | Referência                           |
| LLM2Vec / GRIT              | C          | Métodos (ICLR 2025)        | 2026-09-10    | Referência                           |
| lit-review-mcp              | D          | Aberto                     | 2026-09-10    | Ativo                                |
| ydzat-literature-review-mcp | D          | Aberto                     | 2026-09-10    | Ativo                                |
| review-mcp                  | D          | Aberto                     | 2026-09-10    | Ativo                                |
| academic-search-mcp         | D          | Aberto (npm)               | 2026-09-10    | Ativo                                |
| paper-distill-mcp           | D          | Aberto                     | 2026-09-10    | Ativo                                |
| PAPER-SQL                   | D          | Aberto                     | 2026-09-10    | Ativo                                |
| citecheck                   | D          | Aberto (arXiv 2603.17339)  | 2026-09-10    | Ativo                                |
| JARVIS Research OS          | E          | MIT / requer Gemini API    | 2026-09-10    | Ativo                                |
| prismAId                    | E          | Apache / requer API LLM    | 2026-09-10    | Ativo                                |
| LatteReview                 | E          | Aberto / requer LLM        | 2026-09-10    | Ativo                                |
| ReviewAid                   | E          | Aberto                     | 2026-09-10    | Ativo                                |
| SWARM-SLR AIssistant        | E          | Aberto (arXiv 2603.05177)  | 2026-09-10    | Ativo                                |
| **EmbedSLR** v1.0 / v2.0    | E          | Aberto, Python (SoftwareX) | 2026-09-10    | Ativo                                |
| PaperQA2                    | E          | Apache (FutureHouse)       | 2026-09-10    | Ativo                                |
| Paper Circle                | E          | Aberto (arXiv 2604.06170)  | 2026-09-10    | Ativo                                |
| CE-RAG                      | E          | Publicado                  | 2026-09-10    | Ativo                                |
| Agentic AutoSurvey          | E          | Publicado                  | 2026-09-10    | Ativo                                |

### 3.1 Adições em relação ao mapeamento anterior

Três ferramentas **não constavam** do `papers/novelty-analysis.md` e foram incorporadas:

- **EmbedSLR** (SoftwareX, duas publicações: v1.0 DOI `10.1016/j.softx.2025.102416`;
  v2.0 DOI `10.1016/j.softx.2026.102563`). É o concorrente filosoficamente mais próximo:
  open source, Python, baseado em embeddings, CPU-friendly, com ênfase em reprodutibilidade.
  A v2.0 adiciona consenso entre múltiplos modelos de embedding — publicações escolhidas por
  consenso superam as escolhidas por modelo individual. **Diferença central:** o EmbedSLR faz
  _screening_ do que o usuário importa; não faz busca multi-fonte.
- **citecheck** (arXiv 2603.17339) — MCP server para verificação e reparo bibliográfico
  automatizado. Não é SLR completo, mas pertence à Categoria D.
- **PaperQA2** (FutureHouse, arXiv 2409.13740) — agente de literatura com desempenho
  sobre-humano no benchmark LitQA2 (85,2% de precisão, contra 73,8% de especialistas humanos).
  Opera sobre texto completo, não apenas abstracts.

---

## 4. Matriz comparativa

> **Correção importante em relação à versão anterior:** a linha "Fontes de busca" afirmava
> "AH 16". O pipeline do Academic Hunter consulta **7** fontes em paralelo
> (`arxiv`, `crossref`, `openalex`, `semanticscholar`, `core_ac`, `dblp`, `doaj`). Outras 8
> são acessíveis **sob demanda** por tools MCP (Europe PMC, OpenCitations, Unpaywall,
> Lens.org, OpenAIRE, bioRxiv, medRxiv, DataCite) — não participam da busca automática.
> A versão anterior também listava um "ClinicalTrials.gov" que não existe em nenhuma linha
> de código.

| Critério                         | AH                 | ASReview   | JARVIS      | EmbedSLR               | Elicit     | Scite         | Rayyan     | Covidence |
| -------------------------------- | ------------------ | ---------- | ----------- | ---------------------- | ---------- | ------------- | ---------- | --------- |
| Open source                      | ✅ MIT             | ✅ Apache  | ✅ MIT      | ✅                     | ❌         | ❌            | ❌         | ❌        |
| Custo                            | Zero               | Zero       | Zero¹       | Zero                   | ~US$14/mês | ~US$12–20/mês | Freemium   | Pago      |
| Fontes **no pipeline**           | **7**              | 1          | 5           | 0²                     | 1          | 1             | 1–3        | 1–3       |
| Fontes acessíveis no total       | 15                 | 1          | 5           | 0²                     | 1          | 1             | 1–3        | 1–3       |
| Pipeline SLR completo            | ✅                 | Só triagem | ✅          | Só triagem             | ❌         | ❌            | Só triagem | Parcial   |
| Sem dependência de LLM           | ✅                 | ✅         | ❌ (Gemini) | ✅                     | ❌         | ❌            | N/A        | N/A       |
| Scoring semântico configurável   | ✅ Weight-Bleeding | ❌         | ❌          | Consenso entre modelos | ❌         | ❌            | ❌         | ❌        |
| MCP server                       | ✅ 37 tools        | ❌         | ✅ 15 tools | ❌                     | ❌         | REST paga     | ❌         | ❌        |
| Offline / CPU-only               | ✅                 | ✅         | ❌          | ✅                     | ❌         | ❌            | ❌         | ❌        |
| Clustering temático              | ✅ BERTopic        | ❌         | ❌          | ❌                     | ❌         | ❌            | ❌         | ❌        |
| Detecção de novidade             | ✅                 | ❌         | ❌          | ❌                     | ❌         | ❌            | ❌         | ❌        |
| Landscape 2D (UMAP)              | ✅                 | ❌         | ❌          | ✅ visualização        | ❌         | ❌            | ❌         | ❌        |
| PRISMA automático                | ✅                 | ❌         | ✅          | ❌                     | ❌         | ❌            | ✅         | ✅        |
| Texto completo (não só abstract) | ❌                 | ❌         | ✅          | ❌                     | ❌         | ✅            | ❌         | ❌        |
| Triagem colaborativa             | ❌                 | ✅         | ❌          | ✅ (simulada)          | ❌         | ❌            | ✅         | ✅        |

¹ JARVIS é MIT, mas seu pipeline central requer Gemini API.
² EmbedSLR não busca: faz triagem do corpus que o usuário fornece.

### 4.1 Leitura honesta da matriz

O Academic Hunter **lidera em cobertura multi-fonte, ausência de dependência de LLM,
scoring configurável, superfície MCP e análises com modelo único**. Isso é real e verificável.

**Onde ele perde, e o artigo precisa dizer:**

- **Não processa texto completo.** Todo o pipeline opera sobre título + abstract. PaperQA2,
  Scite e JARVIS vão além.
- **Sem camada de LLM.** LatteReview, SWARM-SLR, Agentic AutoSurvey e PaperQA2 fazem
  triagem, extração e síntese com LLM. O AH não — por escolha de design, mas é uma lacuna funcional.
- **Sem avaliação de qualidade de retrieval.** Não há nDCG, recall@k ou benchmark contra
  qrels rotulados. Os concorrentes publicados (EmbedSLR, PaperQA2) reportam essas métricas.
- **Triagem é o ponto fraco.** O `KeywordScreener` é um stub que retorna `1.0` fixo.
- **Sem colaboração multi-revisor.** Rayyan, Covidence e ASReview têm; o AH não.

---

## 5. Posicionamento

### 5.1 A tese defensável: unicidade por fonte

Um estudo comparativo de 2025–2026 observou que **SciSpace, Consensus e Ai2 Paper Finder
retornam resultados quase idênticos (~40% de unicidade)** porque todos consultam o mesmo
banco subjacente — Semantic Scholar. Elicit e Undermind chegam a ~80% de unicidade por
surfarem fontes mais raras. O mesmo estudo conclui que **nenhuma ferramenta domina**
claramente; são complementares.

Isso é o argumento mais forte e mais verificável a favor do Academic Hunter: ele agrega
**7 fontes independentes**, atacando diretamente o viés de fonte única documentado nos
concorrentes. **Este argumento ainda não foi medido** — ver a tarefa de experimento de
unicidade por fonte (§6).

### 5.2 Posicionamento por eixo, não por totalidade

A afirmação "o AH é superior" só se sustenta se for recortada por eixo:

| Eixo                              | Veredito                                              |
| --------------------------------- | ----------------------------------------------------- |
| Cobertura multi-fonte no pipeline | **Superior** (7 vs 1–5)                               |
| Custo e independência de API      | **Superior** (zero vs API key obrigatória)            |
| Escopo configurável sem retreinar | **Superior** (Weight-Bleeding é original)             |
| Integração com agentes (MCP)      | **Superior em superfície** (37 tools vs 15 do JARVIS) |
| Triagem e extração                | **Inferior** (sem LLM, só abstracts, screener stub)   |
| Avaliação de qualidade            | **Inferior** (sem nDCG/recall@k publicados)           |
| Colaboração                       | **Inferior** (mono-usuário)                           |

Um artigo que afirmar superioridade global será derrubado na revisão pela primeira lacuna.
Um artigo que afirmar superioridade **nos eixos em que ela existe**, e declarar os demais
como trabalho futuro, é defensável.

### 5.3 Sobre a originalidade

A contribuição metodológica original é o **Weight-Bleeding** — ponderação semântica
configurável por interpolação de centroide no espaço de embeddings, sem GPU, sem labels e
sem treino. A §3.13 do paper de conferência documenta que ele **não é equivalente** à
repetição literal de termos (ρ = −0.2242); são operações distintas que produzem rankings
distintos. Isso é uma delimitação de escopo, não um defeito — mas precisa ser dito.

Nenhum paper de 2025–2026 combina SLR + ponderação configurável + MCP.

---

## 6. Lacunas deste mapeamento

1. **O experimento de unicidade por fonte não foi executado.** É o que sustentaria a tese da
   §5.1 com dado próprio em vez de literatura de terceiros.
2. **Ferramentas comerciais não foram testadas diretamente** — avaliação por documentação.
3. **Sem protocolo de revisão formal** — é mapeamento exploratório, não SLR (ver §1.4).
4. **Cobertura de MCP servers é instável** — o ecossistema muda semanalmente; a §3 tem data
   de verificação justamente por isso.
5. **Faltam métricas comparativas de desempenho** (tempo, recall, precisão) entre o AH e os
   concorrentes executáveis (ASReview, EmbedSLR, PaperQA2).

---

## 7. Referências das ferramentas

- ASReview — van de Schoot et al., _Nature Machine Intelligence_, 2021. Preprint: arXiv 2006.12166.
- EmbedSLR v1.0 — _SoftwareX_, 2025. DOI `10.1016/j.softx.2025.102416`.
- EmbedSLR v2.0 — _SoftwareX_, 2026. DOI `10.1016/j.softx.2026.102563`.
- PaperQA2 — Skarlinski et al., arXiv 2409.13740.
- LatteReview — Rahman et al., arXiv 2501.05468.
- SWARM-SLR AIssistant — arXiv 2603.05177.
- Open-Source Agentic Hybrid RAG — arXiv 2508.05660.
- Paper Circle — arXiv 2604.06170.
- citecheck — arXiv 2603.17339.
- Automating SLR (survey) — arXiv 2108.12922 / _Information and Software Technology_, 2021.
- AI for Literature Reviews — arXiv 2402.08565.
- SIF — Arora et al., ICLR 2017.
- SGPT — Muennighoff, EMNLP 2022.
- Echo embeddings — Springer et al., ICLR 2025. arXiv 2402.15449.
- LLM2Vec — BehnamGhader et al., ICLR 2025. GRIT — Muennighoff et al., ICLR 2025.
