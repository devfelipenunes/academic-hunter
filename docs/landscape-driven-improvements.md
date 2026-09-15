# Melhorias e Inovação a partir do Landscape

**Criado em:** 2026-09-10
**Base:** mapeamento de 37 ferramentas concorrentes (o mapeamento não acompanha este repositório)
**Relação com outros docs:** `docs/roadmap.md` parte da dívida técnica interna. Este documento
parte do **que os concorrentes fazem** — o que copiar, o que aprofundar e o que ninguém faz ainda.

---

## 1. O que cada concorrente ensina

| Ferramenta                                  | O que faz bem                                                                                         | Lição para o AH                                                                   |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| **EmbedSLR** (SoftwareX, v1 2025 / v2 2026) | Consenso entre múltiplos modelos de embedding supera modelo individual — resultado medido e publicado | O AH usa **um** modelo (MiniLM). Ensemble é ganho barato e validado por terceiros |
| **PaperQA2** (FutureHouse)                  | Full-text + RAG agêntico; 85,2% no LitQA2 vs 73,8% de PhDs                                            | O AH só vê título + abstract. Teto de qualidade limitado                          |
| **LatteReview**                             | Triagem e extração por agentes LLM especializados                                                     | O screening do AH é o ponto mais fraco (stub)                                     |
| **JARVIS Research OS**                      | PageRank de citações, detecção de contradição, LangGraph com retry                                    | O AH tem só contagem bruta de citações                                            |
| **CE-RAG**                                  | Ranking multi-fator: `α·S_em + β·S_cit + γ·S_rec + δ·S_aud`                                           | O AH tem 2 sinais; a literatura usa 4+ de forma explícita                         |
| **Agentic AutoSurvey**                      | Gera 20–30 queries por tópico e deduplica por sobreposição de título (90%)                            | O AH depende de âncoras manuais                                                   |
| **Undermind**                               | Busca profunda iterativa, 5–20 min, 100–300 papers com justificativa                                  | O AH faz uma passada só                                                           |
| **Paper Circle**                            | Scores explícitos de relevância, novidade, recência e diversidade                                     | O AH tem novidade, mas não diversidade nem recência como sinal                    |
| **SWARM-SLR**                               | Integra ferramentas fragmentadas num workflow único                                                   | Valida a dor que o AH ataca                                                       |
| **ASReview**                                | Active learning com critérios de parada publicados                                                    | O AH não tem active learning nem critério de parada                               |
| **review-mcp**                              | AHP (Analytic Hierarchy Process) para priorização de critérios                                        | Alternativa estruturada à ponderação manual                                       |
| **Scite**                                   | Classifica citações em apoiadoras/contrastantes                                                       | O AH não sabe _como_ um paper é citado                                            |
| **Elicit**                                  | Extração estruturada em tabelas                                                                       | O AH só exporta metadados                                                         |

---

## 2. Melhorias de paridade — não ficar atrás

Ordenadas por **ganho ÷ esforço**:

### 2.1 Ensemble de embeddings com consenso ⭐ maior ganho barato

**A descoberta:** o EmbedSLR v2.0 mediu que publicações escolhidas **por consenso entre
modelos** superam as escolhidas por modelo individual. É um resultado publicado, com métrica.

**O que fazer:** rodar 3–4 modelos (MiniLM, BGE-small, GTE-small, SPECTER2) sobre o mesmo
corpus e combinar por consenso ou média de ranks. O `benchmark_baselines.py` já testa MiniLM,
BGE e GTE — falta o passo de **combinar em vez de comparar**.

**Por que é forte:** ganho imediato de qualidade, custo arquitetural baixo, e é a mesma família
do Weight-Bleeding (que já opera por interpolação de embeddings). Extensão natural: em vez de
um centroide, um **centroide por modelo** com consenso.

**Inovação possível:** ninguém combinou _consenso entre modelos_ (EmbedSLR) com _ponderação
por termos_ (Weight-Bleeding). É uma interseção não explorada.

### 2.2 Full-text via Unpaywall

**A descoberta:** PaperQA2 atinge desempenho sobre-humano trabalhando sobre texto completo. O
AH trabalha com abstracts, que truncam método e resultado.

**O que fazer:** a tool `find_open_access` já consulta o Unpaywall. Falta o pipeline de
ingestão: baixar PDF → extrair texto → chunking → indexar no ChromaDB → retrieval por chunk.

**Custo:** médio-alto (nova dependência PyMuPDF, novo esquema de indexação).
**Ganho:** é a lacuna que mais limita o teto de qualidade.

### 2.3 Triagem assistida por LLM (opcional)

**A descoberta:** LatteReview e SWARM-SLR fazem triagem com LLM e reportam ganho. O
`KeywordScreener` do AH é um stub que retorna `1.0` fixo.

**O que fazer:** nova implementação de `BaseScreener` que recebe os critérios de inclusão em
linguagem natural e emite `include`/`exclude`/`unsure` + justificativa + confiança.

**Restrição de design:** opcional, nunca caminho crítico. O diferencial offline/zero-custo
depende disso.

### 2.4 Ranking multi-fator

**A descoberta:** CE-RAG usa `α·S_em + β·S_cit + γ·S_rec + δ·S_aud` (semântica, citação,
recência, autoridade do autor). O AH soma um bônus logarítmico de citação.

**O que fazer:** generalizar o `compute_hybrid_score` para N fatores com pesos configuráveis
no JSON — reaproveitando o mesmo mecanismo de pesos que o Weight-Bleeding já usa. Recência e
diversidade são sinais triviais de adicionar e hoje estão ausentes.

### 2.5 Grafo de citações

**A descoberta:** JARVIS tem PageRank; PAPER-SQL tem detecção de comunidades; Scite classifica
o _tipo_ de citação.

**O que fazer:** as tools `explore_citation_graph` e `get_citing_papers` já existem mas são
pontuais. Falta construir o grafo e calcular centralidade — o que permite identificar papers
seminais e frentes de pesquisa, não só "quem cita quem".

---

## 3. Aprofundar o que já é diferencial

### 3.1 Weight-Bleeding multi-domínio

A §3.6 do paper de conferência mostra que centroides de domínios distintos são **negativamente
correlacionados** (ρ = −0.746). Hoje o usuário configura **um** domínio por execução.

**Ideia:** compor múltiplos domínios simultaneamente (ex.: 70% blockchain + 30% privacidade),
com o mesmo mecanismo de pesos. Isso é uma extensão direta do método original e **ninguém faz**.
Um artigo cabe aí.

### 3.2 Ponderação aprendida

Hoje todos os pesos são definidos à mão no JSON. SIF usa frequência inversa de corpus, SGPT
usa posição — ambos fixos e não aprendidos. **Aprender os pesos** a partir de um conjunto
rotulado seria contribuição original e diretamente comparável.

Pré-requisito: o conjunto de avaliação da §4.1.

### 3.3 MCP como plataforma, não só conjunto de tools

O AH expõe 44 tools. Quase todos os MCP servers acadêmicos concorrentes expõem 1–5 e fazem uma
coisa. A oportunidade não é ter mais tools, é ser **a camada de retrieval padrão** para agentes
que fazem pesquisa — o que Mishra et al. (SoK Agentic RAG) chamam de risco de _retrieval
misalignment_. O AH já ataca isso por construção.

---

## 4. Inovação — onde ninguém está

Estas são as apostas. Cruzei os 37 itens do mapeamento e **nenhum** faz o seguinte:

### 4.1 Benchmark comparativo de ferramentas SLR ⭐

Não existe avaliação sistemática que compare ferramentas de SLR entre si com métricas comuns.
Cada uma publica sua lista de capacidades. O EmbedSLR mediu a si mesmo; o PaperQA2 mediu a si
mesmo no LitQA2. **Ninguém comparou os dois.**

**Por que cabe:** executável com o que existe (ASReview, EmbedSLR e PaperQA2 são todos
open source e instaláveis). Daria um artigo com método claro: mesmos tópicos, mesmos qrels,
mesmas métricas, em cada ferramenta.

### 4.2 Unicidade de fonte como métrica

Nós já medimos: **93% dos papers vêm de uma única fonte**. Nenhum concorrente publica essa
métrica. A comparação com os ~40% de unicidade entre ferramentas single-source é direta e
reveladora, e não exige treinar nada.

**Ressalva metodológica:** as duas métricas são análogas mas não idênticas (uma compara dois
produtos, a outra mede contribuição dentro de um pipeline). O artigo precisa declarar isso.

### 4.3 Trade-off LLM vs sem-LLM

Ninguém comparou sistematicamente qualidade × custo × reprodutibilidade dos dois regimes.
Existem ferramentas nos dois lados (JARVIS/EmbedSLR/LatteReview com LLM; AH/ASReview sem), mas
nenhum estudo mede o que se ganha e o que se perde.

**Pergunta de pesquisa:** em que ponto o LLM adiciona qualidade que justifique o custo, a perda
de reprodutibilidade e a dependência de API?

### 4.4 Auditoria de reprodutibilidade

Uma contribuição inesperada e viável: **nenhuma ferramenta do mapeamento publica verificação de
reprodutibilidade dos próprios números.** No caso do AH descobrimos, auditando, que três
conjuntos de resultados nos papers não eram reproduzíveis (script ausente, sinais invertidos,
dados contradizendo o texto).

**Ideia:** um protocolo de auditoria para ferramentas de SLR — "seus números sobrevivem à
reexecução?" — aplicado às ferramentas do mapeamento. É meta-ciência, barato de executar, e
ninguém fez.

---

## 5. Priorização

| Ordem | Item                                      | Tipo     | Esforço | Por quê agora                              |
| ----- | ----------------------------------------- | -------- | ------- | ------------------------------------------ |
| 1     | **Conjunto de avaliação rotulado**        | Fundação | Baixo   | Sem isso, nada abaixo é mensurável         |
| 2     | **Ensemble de embeddings (§2.1)**         | Paridade | Baixo   | Ganho validado por terceiros, custo baixo  |
| 3     | **Unicidade de fonte (§4.2)**             | Inovação | Feito   | Dado já existe, só falta escrever          |
| 4     | **Ranking multi-fator (§2.4)**            | Paridade | Baixo   | Reaproveita o mecanismo de pesos existente |
| 5     | **Weight-Bleeding multi-domínio (§3.1)**  | Inovação | Médio   | Extensão natural do método original        |
| 6     | **Trade-off LLM vs sem-LLM (§4.3)**       | Inovação | Médio   | Alto valor de publicação                   |
| 7     | **Triagem por LLM (§2.3)**                | Paridade | Médio   | Maior lacuna funcional                     |
| 8     | **Grafo de citações (§2.5)**              | Paridade | Médio   | JARVIS já tem; é paridade                  |
| 9     | **Full-text (§2.2)**                      | Paridade | Alto    | Maior teto, maior custo                    |
| 10    | **Ponderação aprendida (§3.2)**           | Inovação | Alto    | Depende do item 1                          |
| 11    | **Benchmark de ferramentas (§4.1)**       | Inovação | Alto    | Depende de instalar 3+ concorrentes        |
| 12    | **Auditoria de reprodutibilidade (§4.4)** | Inovação | Médio   | Meta-ciência, diferencial narrativo        |

**Os três primeiros são os que abrem caminho:** o conjunto de avaliação (1) torna tudo
mensurável; o ensemble (2) dá ganho imediato; e a unicidade (3) já está medida e é publicável
sozinha.

---

## 6. Síntese

O Academic Hunter não precisa virar o JARVIS (LLM obrigatório) nem o PaperQA2 (full-text
puro). O espaço dele é **ser o pipeline offline, multi-fonte e configurável** — e as melhorias
acima reforçam exatamente esse eixo em vez de diluí-lo.

A inovação mais promissora não é uma feature: é **medir**. O campo inteiro publica capacidades
sem avaliação. Quem trouxer benchmark, reprodutibilidade e métricas comparativas primeiro
define como o campo se avalia daqui pra frente.
