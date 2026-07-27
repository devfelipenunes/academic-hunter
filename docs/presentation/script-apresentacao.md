# Script de Apresentação — Nova Estrutura (~30 min, 17 slides)

**Público:** Pesquisadores (não necessariamente especialistas em IA)
**Tom:** Conceitual, pouca matemática, muitas analogias, foco no "o que faz" não "como funciona internamente"

---

## PARTE 1 — O PROBLEMA E A VISÃO GERAL (slides 1-3)

---

### SLIDE 1 — Título (1 min)

> "Bom dia. Hoje vou apresentar o **Academic Hunter**, uma plataforma aberta de Revisão Sistemática da Literatura. Diferente das ferramentas existentes, ela combina busca multi-fonte, análise semântica configurável, e integração com agentes de IA — tudo gratuito, tudo local, sem precisar de GPU."

**Título:** Academic Hunter: Revisão Sistemática da Literatura com Análise Semântica Inteligente
**Subtítulo:** 16 bases acadêmicas · 35+ ferramentas de análise · Sem GPU · Open Source

---

### SLIDE 2 — O Problema (2 min)

> "Fazer uma Revisão Sistemática da Literatura hoje é um processo que leva de 6 a 12 meses. O problema não é só o volume de artigos — é que as ferramentas existentes OBRIGAM você a escolher entre:
>
> - **Ferramentas gratuitas mas limitadas** (keyword matching perde sinônimos)
> - **Ferramentas que exigem rotular dados manualmente** (ASReview — você precisa classificar dezenas de papers antes dela aprender)
> - **Ferramentas pagas e fechadas** (Rayyan, Covidence — sem API, sem integração)
> - **Soluções que precisam de GPU caríssima** (cross-encoders)
>
> O Academic Hunter resolve todos esses problemas de uma vez."

**[Mostrar na tela]**

| Problema                                | Consequência                             | Solução no AH                                       |
| --------------------------------------- | ---------------------------------------- | --------------------------------------------------- |
| Keyword matching perde sinônimos        | Artigos relevantes escapam               | Weight-Bleeding: entende conceitos, não só palavras |
| Ferramentas precisam de dados rotulados | Horas perdidas classificando manualmente | Zero-shot: funciona de primeira, sem treino         |
| Ferramentas pagas e sem API             | Sem integração com IA                    | MCP: qualquer agente de IA pode usar                |
| GPU necessária para análise semântica   | Custo alto, setup complexo               | Roda em CPU, 22MB de modelo                         |
| Busca em uma base só                    | Cobertura parcial                        | 16 bases acadêmicas simultâneas                     |

---

### SLIDE 3 — Visão Geral do Fluxo Completo (2 min)

> "Antes de entrar nos detalhes técnicos, quero mostrar o FLUXO COMPLETO do Academic Hunter — do momento que você define um tópico até ter os insights prontos.
>
> O fluxo tem 4 etapas principais:
>
> **1. CONFIGURAR** — Você define o que quer pesquisar num arquivo JSON simples. Diz quais são os termos principais do seu domínio e quanto peso cada um tem.
>
> **2. BUSCAR** — O sistema consulta 16 bases acadêmicas em paralelo, baixa milhares de artigos, remove duplicatas.
>
> **3. ANALISAR** — Esta é a parte mais poderosa. Usando um modelo de IA de 22MB (chamado MiniLM), o sistema faz 12 análises diferentes automaticamente: ranqueia relevância, agrupa por tema, detecta papers inovadores, mostra tendências ao longo do tempo, gera resumos, identifica duplicatas semânticas, e cria um mapa 2D da produção científica.
>
> **4. EXPORTAR** — Os resultados saem em qualquer formato: CSV, BibTeX, RIS, Markdown, PRISMA. E pode salvar direto no seu Obsidian.
>
> E o mais importante: **cada uma dessas análises pode ser chamada por um agente de IA** (Claude, ChatGPT) através do protocolo MCP — o novo padrão da indústria para conectar IAs a ferramentas."

**[Mostrar diagrama do fluxo]**

```
CONFIG → BUSCA (16 bases) → ANALISA (12 análises MiniLM) → EXPORTA
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
               MCP Server              Agentes IA
             (35+ ferramentas)       (Claude, GPT, etc.)
```

---

## PARTE 2 — O SOFTWARE EM AÇÃO (slides 4-6)

---

### SLIDE 4 — Busca Multi-Fonte (2 min)

> "Vamos ver cada etapa em mais detalhe. Primeiro: a busca.
>
> Quando você define uma configuração de busca, o Academic Hunter dispara consultas simultâneas para **16 fontes acadêmicas**:
>
> **Bases tradicionais:** arXiv, Crossref, PubMed/Europe PMC, DBLP, DOAJ
> **APIs inteligentes:** Semantic Scholar, OpenAlex, CORE
> **Dados complementares:** OpenCitations (citações), Unpaywall (acesso aberto)
> **Patentes:** Lens.org
> **Preprints:** bioRxiv, medRxiv
> **Dados de pesquisa:** OpenAIRE (grants), DataCite (datasets), 
> **Identidade:** ORCID (pesquisadores)
>
> Tudo em paralelo, com limite de taxa inteligente para não sobrecarregar as APIs. O resultado é consolidado, deduplicado, e pronto para análise."

---

### SLIDE 5 — O Ecossistema MCP (2 min)

> "Aqui está talvez o diferencial mais importante do Academic Hunter: ele é um **servidor MCP**.
>
> MCP significa Model Context Protocol — é um padrão aberto, criado pela Anthropic e doado pra Linux Foundation em 2025, que permite que QUALQUER agente de IA (Claude, ChatGPT, Gemini, LangChain) se conecte a ferramentas externas de forma padronizada.
>
> O Academic Hunter expõe **35+ ferramentas, 4 recursos e 2 templates de prompt** via MCP. Isso significa que:
>
> - Um pesquisador pode pedir pro Claude: 'Faça uma revisão sobre CBDC'
> - O Claude planeia: descobre jargão → configura busca → executa → analisa resultados → exporta
> - O Claude chama cada ferramenta MCP na sequência correta
> - O pesquisador só VALIDA o resultado final
>
> É como ter um assistente de pesquisa que sabe usar todas as ferramentas do Academic Hunter automaticamente."

**[Mostrar exemplo de diálogo]**

```
Pesquisador: "Faça uma SLR sobre impacto de CBDCs na estabilidade financeira"

Claude (via MCP):
  → quick_topic_discovery("CBDC financial stability")
  → update_config({anchors: {...}, weights: {...}})
  → run_search()
  → semantic_search("CBDC bank disintermediation")
  → cluster_papers()
  → find_novel_papers()
  → visualize_landscape()
  → export_report("csv")
  → export_to_obsidian("CBDC Review")

Pesquisador (valida o resultado em 15 min em vez de 6 meses)
```

---

### SLIDE 6 — Posicionamento: O que Academic Hunter NÃO é (1 min)

> "É importante entender o que Academic Hunter é e o que ele NÃO é:
>
> - **NÃO é um LLM** — ele não gera texto, não inventa respostas, não 'alucina'
> - **NÃO é um agente** — ele é uma CAIXA DE FERRAMENTAS que um agente usa
> - **NÃO substitui o pesquisador** — ele ACELERA o trabalho manual, não toma decisões
>
> O que ele É:
>
> - É um **motor de busca e análise** que entende o SIGNIFICADO dos textos, não só as palavras
> - É um **servidor de ferramentas** que qualquer IA pode usar via protocolo padrão
> - É um **pipeline SLR completo** que roda sem IA também
>
> Na taxonomia acadêmica: Academic Hunter é um **MCP Tool Server especializado em IR acadêmico** que **viabiliza Agentic RAG** — o agente é o LLM externo que orquestra as ferramentas."

---

## PARTE 3 — AS FUNCIONALIDADES MINILM (slides 7-10)

---

### SLIDE 7 — Embeddings: a "impressão digital" dos textos (2 min)

> "Para entender as análises que o sistema faz, primeiro precisa entender o conceito de **embeddings**.
>
> Um embedding é uma **impressão digital matemática** de um texto. Imagine que cada artigo vira um vetor de 384 números. Artigos sobre temas parecidos geram vetores PARECIDOS — ficam próximos uns dos outros num espaço multidimensional.
>
> É como um mapa da cidade: artigos sobre 'deep learning' ficam no bairro da inteligência artificial, artigos sobre 'blockchain' ficam no bairro de criptomoedas. A distância entre eles no mapa reflete a distância semântica entre os temas.
>
> O modelo que usamos (all-MiniLM-L6-v2) tem apenas 22 milhões de parâmetros — cabe num arquivo de 22MB. Roda em QUALQUER computador, sem GPU. E é gratuito."

**[Mostrar analogia visual]**

```
     Blockchain ●─────────● CBDC
                     ┌────┘
      Bitcoin ●──────┘

                     Deep Learning ●─────● Transformers
                                            │
                              NLP ●────────┘
```

---

### SLIDE 8 — Search e Clustering (2 min)

> "Com esses embeddings, o Academic Hunter faz duas coisas fundamentalmente diferentes de ferramentas tradicionais:
>
> **1. BUSCA SEMÂNTICA** (`semantic_search`)
> Em vez de procurar PALAVRAS exatas, ele procura CONCEITOS. 'Impacto de moeda digital nos bancos' encontra artigos sobre CBDC e desintermediação financeira — mesmo que as palavras exatas não apareçam.
>
> **2. AGRUPAMENTO AUTOMÁTICO** (`cluster_papers`)
> O sistema agrupa milhares de artigos em TEMAS automaticamente, sem você precisar definir categorias antes. Ele descobre a estrutura da sua área de pesquisa. Por exemplo, numa busca sobre 'IA na saúde', ele pode encontrar clusters como: diagnóstico por imagem, prontuários eletrônicos, descoberta de medicamentos, ética em IA.
>
> Além disso, o `trending_topics` mostra quais são os tópicos mais frequentes — um rápido 'raio-x' da sua base."

---

### SLIDE 9 — Descoberta: Novidade, Evolução e Mapa (2 min)

> "Três funcionalidades que ajudam o pesquisador a enxergar o que NÃO está óbvio:
>
> **1. DETECÇÃO DE NOVIDADE** (`find_novel_papers`)
> O sistema identifica artigos que são DIFERENTES de tudo que já foi publicado — papers que não se encaixam em nenhum cluster existente. Isso é valioso porque esses papers frequentemente representam NOVAS ABORDAGENS, pesquisa interdisciplinar, ou tendências emergentes. O algoritmo de detecção de outliers (EllipticEnvelope) funciona como um 'radar' que aponta o que foge do padrão.
>
> **2. EVOLUÇÃO TEMPORAL** (`topic_evolution`)
> Mostra como os tópicos mudaram ao longo dos anos. Um tema que cresce sugere uma área quente. Um que encolhe sugere maturidade ou declínio. Essencial para entender a dinâmica de um campo.
>
> **3. MAPA DA PESQUISA** (`visualize_landscape`)
> Projeta TODOS os artigos num mapa 2D interativo. Cada ponto é um paper. Artigos próximos = temas similares. Dá pra ver rapidamente: onde tem mais papers (áreas consolidadas), onde tem lacunas (oportunidades de pesquisa), papers isolados (tópicos nicho)."

---

### SLIDE 10 — Síntese e Qualidade (2 min)

> "Completando as funcionalidades MiniLM:
>
> **RESUMO AUTOMÁTICO** (`summarize_paper`)
> Dado um DOI, o sistema extrai as sentenças MAIS REPRESENTATIVAS do abstract usando o algoritmo MMR (Maximal Marginal Relevance). Ele seleciona sentenças que são: (1) relevantes ao tema central do paper e (2) NÃO redundantes entre si. O resultado é um resumo de 3-5 sentenças que captura a essência do trabalho.
>
> **DUPLICATAS SEMÂNTICAS** (`semantic_dedup`)
> Além de remover duplicatas por DOI (que todo mundo faz), o sistema detecta papers que são virtualmente idênticos mas têm DOIs diferentes — como um preprint e sua versão publicada, ou traduções. Ele compara os embeddings e agrupa papers com similaridade acima de 88%.
>
> **RE-RANQUEAMENTO** (`rerank_search`)
> Opcionalmente, o sistema pode usar um modelo mais preciso (cross-encoder) para re-ranquear os top-20 resultados. É mais lento (~7x) mas mais preciso — útil para a etapa final de seleção."

---

## PARTE 4 — WEIGHT-BLEEDING (slides 11-13)

---

### SLIDE 11 — O Problema que o Weight-Bleeding Resolve (2 min)

> "Agora vamos ao coração técnico: **Weight-Bleeding**.
>
> Lembram que eu falei que embeddings transformam textos em vetores de números? Pois bem: o método padrão para criar esses vetores se chama **mean pooling** — ele simplesmente tira a MÉDIA de todos os tokens do texto.
>
> O problema é que a média trata TODAS as palavras igualmente. Numa busca sobre 'repetição de termos em bi-encoders', as palavras 'termo', 'repetição' e 'codificador' têm o mesmo peso. O pesquisador não tem como dizer que 'bi-encoder' é mais importante que 'termo'.
>
> Isso gera dois problemas práticos:
>
> 1. Artigos sobre temas PARECIDOS mas não EXATOS ficam com scores comprimidos — difícil separar o relevante do irrelevante
> 2. O pesquisador não consegue 'guiar' a busca semanticamente
>
> O Weight-Bleeding resolve isso de forma surpreendentemente simples."

**[Analogia]**

```
Mean pooling é como uma pesquisa de opinião onde todo mundo tem 1 voto.

Weight-Bleeding é como dar mais votos para os especialistas no assunto.
```

---

### SLIDE 12 — Como o Weight-Bleeding Funciona (2 min)

> "A ideia é elegantemente simples:
>
> **Se repetir um termo W vezes no texto fizesse ele contribuir W vezes mais, por que não fazer isso diretamente no espaço de embeddings?**
>
> É matematicamente equivalente — mas sem precisar aumentar o tamanho do texto, sem custo computacional extra.
>
> Na prática:
>
> 1. O pesquisador define num arquivo JSON quais são os termos importantes do seu domínio e qual o peso de cada um
> 2. O sistema calcula um **centroide ponderado** — uma 'posição alvo' no espaço de embeddings que reflete os pesos definidos
> 3. Cada artigo é comparado com esse centroide: quanto mais próximo, mais relevante
>
> O ajuste final é uma **transformação de raiz quadrada** no score de similaridade — que resolve o problema dos scores comprimidos sem alterar a ordem dos resultados.
>
> Tudo isso roda em CPU, leva milissegundos por artigo, e não precisa de nenhum dado de treinamento."

**[Mostrar exemplo simplificado]**

```
Configuração para busca sobre "CBDC":
{
  "CBDC": 5.0,        ← termo central, peso alto
  "banco central": 5.0,
  "moeda digital": 5.0,
  "liquidez": 2.0,    ← relevante mas secundário
  "blockchain": 2.0,
  "política": 1.0     ← contexto, peso baixo
}

Resultado: artigos sobre CBDC sobem no ranking.
Artigos sobre blockchain SEM CBDC não são afetados.
```

---

### SLIDE 13 — Resultados Práticos (2 min)

> "O Weight-Bleeding foi validado experimentalmente. Os resultados mais importantes:
>
> **1. MUDA O RANKING** — A ordem dos artigos é significativamente diferente de um bi-encoder puro (correlação de 96.8% — alta mas não perfeita). 40% dos top-10 são diferentes.
>
> **2. ESPECÍFICO DO DOMÍNIO** — Uma configuração para 'SLR' e uma para 'Blockchain' produzem rankings NEGATIVAMENTE correlacionados (-0.75). Isso prova que o método não é um viés global — ele realmente REFLETE O DOMÍNIO escolhido.
>
> **3. RESGATA ARTIGOS PERDIDOS** — Com a transformação de raiz quadrada, o sistema aprova 151 artigos vs 92 do baseline — 59 artigos a mais que seriam perdidos.
>
> **4. EFICIÊNCIA** — 7.5x mais rápido que cross-encoder. O centroide é calculado uma vez (0.5 segundos) e cada artigo é milissegundos.
>
> **5. ROBUSTO** — Funciona consistentemente em 3 modelos de embedding diferentes (MiniLM, BGE, GTE). A configuração é estável: valores próximos de parâmetros produzem resultados quase idênticos."

---

## PARTE 5 — O QUE TUDO ISSO SIGNIFICA (slides 14-17)

---

### SLIDE 14 — O Ecossistema Completo (2 min)

> "Vamos juntar todas as peças:
>
> **O Academic Hunter é o ÚNICO sistema que combina:**
>
> ✅ **Pipeline SLR completo** — busca, dedup, scoring, PRISMA — tudo local
> ✅ **16 bases acadêmicas** — a cobertura mais ampla entre ferramentas SLR
> ✅ **35+ ferramentas MCP** — qualquer agente IA pode orquestrar
> ✅ **12 análises MiniLM** — do ranking semântico ao mapa 2D, tudo do mesmo modelo de 22MB
> ✅ **Weight-Bleeding** — controle semântico configurável inédito em bi-encoders
> ✅ **Zero GPU, zero API paga** — roda em qualquer notebook
>
> **Comparado com outras ferramentas:**
>
> | Recurso              | Academic Hunter | ASReview       | Rayyan      | Covidence   |
> | -------------------- | --------------- | -------------- | ----------- | ----------- |
> | Código aberto        | ✅              | ✅             | ❌          | ❌          |
> | Fontes de dados      | 16              | 1 (importação) | 1           | 1           |
> | Scoring semântico    | ✅ WB           | ❌             | ❌          | ❌          |
> | Cluster automático   | ✅              | ❌             | ❌          | ❌          |
> | Detecção de novidade | ✅              | ❌             | ❌          | ❌          |
> | MCP / API para IA    | ✅              | ❌             | ❌          | ❌          |
> | Custo                | Zero            | Zero           | $$$         | $$$$        |
> | GPU necessária       | Não             | Não            | N/A (cloud) | N/A (cloud) |

---

### SLIDE 15 — Posicionamento Acadêmico (1 min)

> "Academic Hunter ocupa uma posição ÚNICA no cenário acadêmico atual:
>
> **Agente de Retrieval vs Ferramenta de Retrieval**
>
> - Não somos um agente de IA — somos as FERRAMENTAS que o agente usa
> - Não substituímos o pesquisador — ACELERAMOS o trabalho dele
> - Não competimos com ChatGPT/Claude — nos INTEGRAMOS a eles via MCP
>
> **Na literatura recente:**
>
> - O survey de Singh et al. (2025) cataloga 7 arquiteturas de Agentic RAG — nenhuma menciona SLR
> - Queen-Bee Agents (2026) propõe agentes especialistas conectados por MCP — Academic Hunter é uma dessas 'abelhas'
> - O SoK de Mishra et al. (2026) identifica 'retrieval misalignment' como risco crítico — Weight-Bleeding MITIGA esse risco
> - Nenhum paper de 2025-2026 combina SLR + Weight-Bleeding + MCP

---

### SLIDE 16 — O que Estamos Construindo (1 min)

> **Publicações:**
>
> 📄 **JOSS** — Journal of Open Source Software
> → Foco: a ferramenta, o ecossistema, como usar
> → 244 linhas, 16 conectores, 35+ tools, 155 testes
>
> 📄 **Conferência** (alvo: EMNLP/ACL/ECIR)
> → Foco: o método Weight-Bleeding, experimentos, baselines
> → 346 linhas, 12 experimentos, 3 modelos, 5 baselines
>
> **Próximos passos:**
>
> - Publicar no PyPI (`pip install academic-hunter`)
> - DOI Zenodo definitivo
> - ORCID real
> - Validação humana dos resultados (user study)

---

### SLIDE 17 — Obrigado (1 min)

> "Código aberto: **github.com/devfelipenunes/academic-hunter**
> Documentação: **devfelipenunes.github.io/academic-hunter**
>
> Perguntas? Críticas? Sugestões?
>
> **A discussão é o que vai definir os próximos passos.**"

---
