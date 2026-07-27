# Script de Apresentação — Academic Hunter

**Duração:** ~40 minutos (20 slides)
**Público:** Pesquisadores (não necessariamente especialistas em IA)
**Tom:** Conceitual, constrói conhecimento passo a passo

---

## PARTE 1 — O PROBLEMA (slides 1-3, ~5 min)

---

### SLIDE 1 — Título (1 min)

> "Bom dia. Hoje vou apresentar o **Academic Hunter**, uma plataforma aberta de Revisão Sistemática da Literatura.
>
> A gente reduz o tempo de uma SLR de **6 a 12 meses** para **15 minutos** — não substituindo o pesquisador, mas automatizando o trabalho braçal.
>
> Tudo open source, gratuito, e roda em qualquer notebook — sem GPU, sem API paga."

**[Avançar]**

---

### SLIDE 2 — O Problema (2 min)

> **6 a 12 meses.** Por quê? As ferramentas existentes obrigam você a escolher:
>
> **Keyword matching** — perde sinônimos. 'Moeda digital' não encontra 'CBDC'.
> **Rotular dados** — ASReview exige classificar dezenas de papers manualmente.
> **Pagos e fechados** — Rayyan/Covidence: US$ 100-500/mês, sem API.
> **Dependem de GPU** — modelos de IA precisam de placa de vídeo cara.
>
> Academic Hunter resolve TUDO isso — de graça."

**[Avançar]**

---

### SLIDE 3 — O Fluxo (1.5 min)

> "Antes de mostrar as funcionalidades: o fluxo completo — 4 etapas:
>
> **1. Configurar** — o pesquisador só diz o tópico. O sistema descobre os jargões.
> **2. Buscar** — 16 bases acadêmicas em paralelo. Minutos.
> **3. Analisar** — 12 análises automáticas com IA.
> **4. Exportar** — CSV, BibTeX, RIS, JSON, Markdown, Obsidian.
>
> O mais importante: cada análise pode ser chamada por um agente de IA automaticamente."

**[Avançar — Parte 2]**

---

## PARTE 2 — O DIFERENCIAL (slides 4-8, ~8 min)

---

### SLIDE 4 — Integração com IA (MCP) (2 min)

> "O Academic Hunter implementa o **MCP — Model Context Protocol**. É um padrão aberto, criado pela Anthropic, adotado pela Linux Foundation, OpenAI e Google. Permite que QUALQUER agente de IA se conecte a ferramentas externas.
>
> O Academic Hunter expõe **35+ ferramentas, 4 recursos e 2 templates** via MCP. Um agente de IA pode chamar cada funcionalidade que vou mostrar automaticamente.
>
> É como ter um assistente de pesquisa que sabe usar TODAS as ferramentas do Academic Hunter e planeja sozinho a melhor sequência para cada tarefa."

**[Avançar]**

---

### SLIDE 5 — MCP em Ação (2 min)

> "Na prática: o pesquisador pede pro Claude fazer uma revisão. O Claude planeia e executa:
>
> 1. quick_topic_discovery — descobre jargões
> 2. semantic_search — busca por conceito
> 3. cluster_papers — agrupa por tema
> 4. find_novel_papers — detecta outliers
> 5. visualize_landscape — gera mapa 2D
> 6. export_to_obsidian — salva no Second Brain
>
> **Resultado:** pesquisador valida em 15 minutos. Claude orquestra 35+ ferramentas. O pesquisador só valida."

**[Avançar]**

---

### SLIDE 6 — 16 Fontes (1.5 min)

> "Busca em **16 fontes simultâneas**: arXiv, Crossref, Europe PMC, Semantic Scholar, OpenAlex, CORE, DBLP, DOAJ, OpenCitations, Unpaywall, Lens.org, OpenAIRE, bioRxiv, medRxiv, DataCite, ORCID. Maior cobertura entre ferramentas SLR."

**[Avançar]**

---

### SLIDE 7 — Posicionamento (1 min)

> "❌ **Não é ChatGPT** — não gera texto, não alucina.
> ❌ **Não é agente autônomo** — é caixa de ferramentas que um agente IA usa.
> ✅ **É motor de busca semântica** — entende significado, não só palavras.
> ✅ **Viabiliza Agentic RAG** — agente IA orquestra ferramentas especializadas."

**[Avançar]**

---

### SLIDE 8 — Arquitetura (1.5 min)

> "Arquitetura hexagonal baseada em plugins. **MCP Server** → **Core Domain** → **Plugin Layer** → **Infrastructure**. Cada conector é um plugin independente — adicionar nova fonte não exige mexer no núcleo."

**[Avançar — Parte 3]**

---

## PARTE 3 — COMO FUNCIONA (slides 9-13, ~10 min)

---

### SLIDE 9 — Embeddings (2 min)

> "Pra entender as análises, primeiro precisa entender **embeddings**.
>
> É uma **impressão digital matemática** do texto. Cada artigo vira um vetor de **384 números**. Artigos sobre temas parecidos geram vetores parecidos.
>
> **Analogia:** mapa da cidade. IA fica num bairro, Blockchain noutro. A distância reflete a distância entre os assuntos.
>
> **Dados REAIS:** 100 papers projetados em 2D. CBDC (verde), IA (azul), outliers (vermelho).
>
> O modelo faz tudo com **22MB** — menor que uma foto. Roda em qualquer computador."

**[Avançar]**

---

### SLIDE 10 — 12× MiniLM (1.5 min)

> "O **mesmo modelo de 22MB** alimenta **12 funcionalidades diferentes**:
>
> **Scoring:** ranqueamento inteligente.
> **Search:** busca por conceito, re-ranqueamento, snowballing.
> **Analysis:** clusters, outliers, evolução, mapa 2D, sumarização, dedup.
>
> Zero GPU. Zero API paga. Nenhuma outra SLR tool faz isso."

**[Avançar]**

---

### SLIDE 11 — Busca Semântica (2 min)

> "Passo a passo da semantic_search:
>
> Pergunta → embedding (384 números) → compara com 7.338 papers via similaridade cosseno → top-3.
>
> **Exemplo real:** 'CBDC impact on bank disintermediation'. Nenhum resultado contém 'disintermediation' — o sistema entendeu o CONCEITO."

**[Avançar]**

---

### SLIDE 12 — Clusters (2 min)

> "cluster_papers com BERTopic em 3 etapas:
>
> **1. UMAP** — reduz 384 dimensões preservando distâncias.
> **2. HDBSCAN** — agrupa por densidade, sem precisar dizer quantos clusters.
> **3. c-TF-IDF** — nomeia cada cluster automaticamente.
>
> **Exemplo real:** 50 papers → 3 clusters (Revisão Sistemática, Embeddings, IA) + 2 outliers (GNNs, Ethereum)."

**[Avançar]**

---

### SLIDE 13 — Mais Funcionalidades (2 min)

> **Detecção de novidade:** EllipticEnvelope — papers que fogem da distribuição são marcados como outliers.
> **Evolução temporal:** dados reais — de 3 papers (2020) para 12 (2025). Crescimento de 4x.
> **Resumo, dedup, re-rank:** summarize_paper com MMR, semantic_dedup por similaridade >88%, rerank com cross-encoder."

**[Avançar — Parte 4]**

---

## PARTE 4 — O MÉTODO (slides 14-17, ~10 min)

---

### SLIDE 14 — Mean Pooling (2 min)

> "Bi-encoders usam **mean pooling**: embedding final = média simples de cada palavra. Todas as palavras têm o MESMO peso.
>
> Na frase 'O bi-encoder usa repetição', 'O' e 'de' têm o mesmo peso que 'bi-encoder'. O embedding não reflete a importância real.
>
> **Consequências:** scores comprimidos + sem controle para o pesquisador."

**[Avançar]**

---

### SLIDE 15 — Solução em 5 Passos (2.5 min)

> "Se repetir um termo W vezes fizesse ele contribuir W vezes mais, simulamos isso no espaço de embeddings — sem custo, sem GPU.
>
> **1.** JSON com termos e pesos: CBDC=5, moeda digital=5, liquidez=2.
> **2.** Centroide ponderado = média dos embeddings, cada um multiplicado pelo peso.
> **3.** Cada artigo comparado com esse centroide.
> **4.** Artigos sobre CBDC sobem. Blockchain sem CBDC não é afetado.
> **5.** Raiz quadrada no score final resolve compressão."

**[Avançar]**

---

### SLIDE 16 — Raiz Quadrada (2 min)

> "Similaridades cosseno em 384 dimensões se concentram entre 0.05-0.50.
>
> **Antes (linear):** relevante (0.30) → 3.0. Irrelevante (0.25) → 2.5. Quase invisível. Ambos perdidos no threshold.
>
> **Depois (raiz quadrada):** relevante → 5.48. Irrelevante → 5.00. Diferença clara.
>
> **Impacto:** 59 papers a mais aprovados com WB + sqrt."

**[Avançar]**

---

### SLIDE 17 — Resultados (2 min)

> **96.8%** — Spearman vs vanilla. Ranking MUDA: 40% dos top-10 diferentes.
> **-0.75** — correlação NEGATIVA entre domínios SLR e Blockchain. Efeito é específico, não viés global.
> **7.5× mais rápido** que cross-encoder. Consistente em 3 modelos: MiniLM, BGE, GTE."

**[Avançar — Parte 5]**

---

## PARTE 5 — CONTRIBUIÇÃO (slides 18-20, ~4 min)

---

### SLIDE 18 — vs Concorrentes (1.5 min)

> "16 fontes, scoring semântico, clusters, novidade, mapa, MCP — único. Custo zero."

**[Avançar]**

---

### SLIDE 19 — Posicionamento (1 min)

> "Nenhum paper 2025-2026 combina SLR + Weight-Bleeding + MCP. Posição única."

**[Avançar]**

---

### SLIDE 20 — Publicações + CTA (1.5 min)

> "JOSS (ferramenta) + Conferência (método). Código no GitHub. Instalem, testem, contribuam. Perguntas?"

---

## Notas para o apresentador

### Timing

- Parte 1 (slides 1-3): ~5 min — direto ao ponto
- Parte 2 (slides 4-8): ~8 min — MCP é o gancho, gastar tempo aqui
- Parte 3 (slides 9-13): ~10 min — embeddings é o conceito mais importante
- Parte 4 (slides 14-17): ~10 min — ir devagar no slide 16 (sqrt)
- Parte 5 (slides 18-20): ~4 min — fechamento

### Dicas

- **Slide 4** (MCP): primeira vez que o termo aparece. Explicar como "protocolo que permite IAs usarem ferramentas"
- **Slide 5** (diálogo): mostrar com entusiasmo — é o que vende a ferramenta
- **Slide 9** (embeddings): a analogia do mapa da cidade é essencial
- **Slide 15** (solução): não precisa mostrar fórmula — o passo a passo é suficiente
- **Slide 16** (sqrt): mostrar os números com calma
