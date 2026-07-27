# Script de Apresentação — Academic Hunter

**Duração:** ~40 minutos (21 slides)
**Público:** Pesquisadores (não necessariamente especialistas em IA)
**Tom:** Conceitual, entusiasmado mas honesto, foco no "o que faz" não "como funciona"

---

## PARTE 1 — O PROBLEMA (slides 1-4, ~7 min)

---

### SLIDE 1 — Título (1 min)

> "Bom dia. Hoje vou apresentar o **Academic Hunter**, uma plataforma aberta de Revisão Sistemática da Literatura.
>
> O problema que a gente resolve é simples: fazer uma SLR hoje leva de **6 a 12 meses**. A gente reduz isso para **15 minutos** — não porque a gente substitui o pesquisador, mas porque a gente automatiza o trabalho braçal de busca, triagem e análise inicial.
>
> E tudo isso é **open source, gratuito, e roda em qualquer notebook — sem GPU, sem API paga**."

**[Avançar]**

---

### SLIDE 2 — O Problema (1.5 min)

> "Vamos começar pelo problema.
>
> **6 a 12 meses.** É quanto tempo uma Revisão Sistemática leva hoje. E por que? Porque as ferramentas que existem obrigam você a escolher entre:
>
> - **Keyword matching** — que perde sinônimos. Se você busca "CBDC" e o artigo fala "moeda digital do banco central", você perde o artigo.
> - **Rotular dados manualmente** — o ASReview exige que você classifique dezenas de papers antes de começar a funcionar.
> - **Pagos e fechados** — Rayyan e Covidence custam de 100 a 500 dólares POR MÊS, são cloud, e não têm API pra integrar com IA.
> - **Dependem de GPU** — modelos de IA precisam de placa de vídeo de mil dólares+.
>
> **Academic Hunter resolve todos esses problemas — de graça.**"

**[Avançar]**

---

### SLIDE 3 — Caso Real via MCP (2 min)

> "Agora vou mostrar como o Academic Hunter funciona na prática — e o fluxo é inteiramente **via MCP**.
>
> O pesquisador não abre terminal, não edita JSON, não configura nada manualmente. Ele simplesmente **pede para o Claude** fazer a revisão:
>
> ```
> Pesquisador: "Faça uma revisão sobre o impacto de CBDCs na estabilidade financeira"
> ```
>
> O Claude — que é um agente de IA conectado ao Academic Hunter via protocolo MCP — **planeia e executa** cada etapa:
>
> 1. **quick_topic_discovery** — descobre os jargões da área automaticamente
> 2. **update_config** — configura âncoras e pesos sem o pesquisador editar JSON
> 3. **run_search** — dispara a busca em 16 fontes simultâneas
> 4. **semantic_search** — explora os resultados por conceito
> 5. **cluster_papers + find_novel_papers** — agrupa por tema e detecta outliers
> 6. **visualize_landscape + export_to_obsidian** — gera o mapa 2D e salva no Second Brain
>
> O resultado: **o pesquisador valida em 15 minutos** o que levaria 6 meses.
>
> **O Claude orquestra 35+ ferramentas MCP. O pesquisador só valida.**"

**[Avançar]**

---

### SLIDE 4 — Fluxo Completo (1.5 min)

> "O fluxo completo tem 4 etapas, representadas neste diagrama:
>
> **1. Configurar** — o pesquisador só diz o tópico. O sistema descobre os jargões.
> **2. Buscar** — 16 bases acadêmicas em paralelo. Milhares de artigos em minutos.
> **3. Analisar** — 12 análises automáticas usando o mesmo modelo de IA.
> **4. Exportar** — CSV, BibTeX, RIS, JSON, Markdown, PRISMA, Obsidian.
>
> E o mais importante: **cada uma dessas análises pode ser chamada por um agente de IA** como Claude ou ChatGPT, através do protocolo MCP — representado aqui no canto superior direito.
>
> O pesquisador não executa o trabalho braçal — ele **valida** o resultado."

**[Avançar — Parte 2]**

---

## PARTE 2 — ARQUITETURA + SOFTWARE (slides 5-7, ~5 min)

---

### SLIDE 5 — Arquitetura Hexagonal (1.5 min)

> "Antes de detalhar as funcionalidades, quero mostrar como o sistema foi construído. A arquitetura é **hexagonal e baseada em plugins** — cada camada tem responsabilidades claras e pode ser substituída independentemente.
>
> **MCP Server** — a camada de interface com agentes de IA. 35+ ferramentas, 4 recursos, 2 prompts, health check, suporte a SSE. Tudo que um agente IA precisa para orquestrar uma SLR.
>
> **Core Domain** — o núcleo do sistema. O modelo de paper, o scorer NLP com Weight-Bleeding, o pipeline manager, e a exportação PRISMA. Isso tudo funciona SEM LLM — o sistema é autônomo.
>
> **Plugin Layer** — a camada de conectores. Cada fonte de dados é um plugin independente. No momento temos 15 conectores, mas adicionar um novo não exige mexer no núcleo. O mesmo vale para screeners, exporters, e o vector store ChromaDB.
>
> **Infrastructure** — SQLite para cache, ChromaDB para vetores, config.json para configuração, env vars para override.
>
> Essa arquitetura permite que o sistema escale horizontalmente — mais conectores, mais análises, mais formatos de exportação — sem nunca precisar reescrever o núcleo."

**[Avançar]**

---

---

### SLIDE 5 — 16 Fontes (1.5 min)

> "Vamos detalhar cada etapa. Primeiro: **a busca**.
>
> O Academic Hunter se conecta a **16 fontes acadêmicas simultaneamente** — é a única ferramenta SLR com essa cobertura. Temos:
>
> - **Bases tradicionais:** arXiv, Crossref, Europe PMC, DBLP, DOAJ
> - **APIs inteligentes:** Semantic Scholar, OpenAlex, CORE
> - **Preprints:** bioRxiv, medRxiv
> - **Dados complementares:** OpenCitations (2 bilhões de links de citação), Unpaywall (acesso aberto)
> - **Patentes:** Lens.org
> - **Grants e dados:** OpenAIRE (3.7 milhões de grants), DataCite, ORCID
>
> Tudo em paralelo, com limite de taxa inteligente para não sobrecarregar as APIs."

**[Avançar]**

---

### SLIDE 6 — MCP (2 min)

> "Aqui está talvez o diferencial mais importante: o Academic Hunter é um **servidor MCP**.
>
> MCP significa **Model Context Protocol** — é um padrão aberto, criado pela Anthropic e adotado pela Linux Foundation, OpenAI e Google. Ele permite que QUALQUER agente de IA se conecte a ferramentas externas de forma padronizada.
>
> **Na prática**, funciona assim: você pede pro Claude fazer uma revisão sobre CBDC. O Claude **planeia** o que precisa ser feito, e chama cada ferramenta do Academic Hunter na sequência correta:
>
> 1. `quick_topic_discovery` — descobre os jargões da área
> 2. `semantic_search` — busca artigos por conceito
> 3. `cluster_papers` — agrupa os resultados por tema
> 4. `find_novel_papers` — detecta artigos fora do padrão
> 5. `visualize_landscape` — gera o mapa 2D da pesquisa
> 6. `export_to_obsidian` — salva no Second Brain
>
> **O pesquisador valida o resultado em 15 minutos.**"

**[Avançar]**

---

### SLIDE 7 — Posicionamento (1.5 min)

> "É importante deixar claro o que o Academic Hunter **é** e o que ele **não é**, porque isso evita expectativas erradas.
>
> ❌ **Não é um ChatGPT** — ele não gera texto, não inventa respostas, não alucina. Ele RECUPERA e ANALISA o que já foi publicado.
>
> ❌ **Não é um agente autônomo** — ele é uma caixa de ferramentas que um agente IA usa.
>
> ✅ **É um motor de busca semântica** — entende o SIGNIFICADO, não só as palavras.
>
> ✅ **É a 'parte inteligente' de um sistema maior** — na literatura, isso se chama Agentic RAG: o agente IA orquestra; o Academic Hunter executa a parte especializada em SLR."

**[Avançar — Parte 3]**

---

## PARTE 3 — FUNCIONALIDADES MINILM (slides 8-12, ~10 min)

---

### SLIDE 8 — Embeddings (2 min)

> "Para entender as análises, primeiro precisa entender o conceito de **embeddings**.
>
> Embedding é uma **impressão digital matemática** de um texto. Cada artigo vira um vetor de **384 números**. Artigos sobre temas parecidos geram vetores parecidos — ficam próximos uns dos outros num espaço multidimensional.
>
> A analogia é um **mapa da cidade**: artigos sobre IA ficam no 'bairro' da inteligência artificial. Blockchain fica noutro bairro. A distância entre eles reflete a distância entre os temas.
>
> **Aqui no slide, vocês estão vendo dados REAIS** — 100 papers do Academic Hunter projetados em 2D. Os pontos verdes são papers sobre CBDC, os azuis são IA/ML, os vermelhos são outliers — papers que não se encaixam em nenhum cluster.
>
> E o modelo que faz tudo isso? **22 megabytes.** Cabe num arquivo menor que uma foto JPEG. Roda em QUALQUER computador."

**[Avançar]**

---

### SLIDE 9 — 12× MiniLM (1.5 min)

> "E aqui está talvez o fato mais impressionante do Academic Hunter: **o mesmo modelo de 22MB alimenta 12 funcionalidades diferentes**.
>
> **Scoring:** Weight-Bleeding (o método de ranqueamento que a gente desenvolveu) e o Semantic Screener (filtro por similaridade).
>
> **Search:** busca semântica por conceito, re-ranqueamento com cross-encoder, e snowballing — encontrar papers relacionados a partir de qualquer artigo.
>
> **Analysis:** clustering temático com BERTopic, detecção de outliers, evolução temporal, mapa 2D com UMAP, tópicos frequentes, dedup semântico, e sumarização automática.
>
> **Tudo do mesmo modelo. Zero GPU. Zero API paga.** Nenhuma outra ferramenta SLR faz isso."

**[Avançar]**

---

### SLIDE 10 — Busca Semântica (2 min)

> "Vamos mergulhar na primeira funcionalidade: **semantic_search**.
>
> O slide mostra o passo a passo. Quando o pesquisador faz uma pergunta, o sistema:
>
> **1.** Transforma a pergunta num embedding — 384 números que representam o significado.
> **2.** Compara esse embedding com os 7.338 papers indexados usando **similaridade cosseno** — basicamente, mede o ângulo entre os vetores.
> **3.** Retorna os top-3 papers com maior similaridade.
>
> Reparem no exemplo real. A pergunta é: 'CBDC impact on bank disintermediation'. A palavra 'disintermediation' NÃO aparece em nenhum dos três resultados — mas o sistema entendeu o conceito e trouxe artigos relevantes.
>
> Isso é a diferença entre buscar por PALAVRAS e buscar por CONCEITOS. O embedding captura o significado, não o texto exato."

**[Avançar]**

---

### SLIDE 11 — Clusters Automáticos (2 min)

> "A segunda funcionalidade em detalhe: **cluster_papers**.
>
> O algoritmo BERTopic funciona em 3 etapas:
>
> **1. UMAP** — reduz as 384 dimensões dos embeddings para um espaço menor, preservando as distâncias entre os papers.
> **2. HDBSCAN** — agrupa os pontos por densidade. Diferente do K-means, ele NÃO precisa que você diga quantos clusters existem. Ele descobre sozinho.
> **3. c-TF-IDF** — para cada cluster, extrai as palavras mais importantes. Isso dá nome aos temas automaticamente.
>
> **Exemplo real:** numa base de 50 papers, o sistema encontrou 3 clusters e 2 outliers. Os clusters são coerentes — revisão sistemática, embeddings, IA — e os outliers são genuinamente diferentes (GNNs, Ethereum).
>
> Isso é **taxonomia automática**. O sistema descobre a estrutura do seu campo de pesquisa sem você definir nada."

**[Avançar]**

---

### SLIDE 12 — Novidade, Evolução e Síntese (2 min)

> "As demais funcionalidades, com mais detalhes:
>
> **Detecção de novidade:** o EllipticEnvelope estima a distribuição matemática dos embeddings. Papers que caem fora dessa distribuição são marcados como outliers. Nos testes, encontramos dois papers sobre GNNs e Ethereum — temas genuinamente diferentes do resto da base.
>
> **Evolução temporal:** dados REAIS da nossa base. De 2020 a 2025, o número de papers cresceu de 3 para 12 — um crescimento de 4x. A área está em expansão.
>
> **Resumo, dedup e re-rank:** funcionalidades de precisão. O summarize_paper usa MMR para extrair as sentenças mais relevantes E não redundantes. O semantic_dedup agrupa papers com mais de 88% de similaridade — pega duplicatas que o DOI não pega. O rerank_search combina MiniLM (rápido) com cross-encoder (preciso) para o melhor dos dois mundos."

**[Avançar — Parte 4]**

---

## PARTE 4 — WEIGHT-BLEEDING (slides 13-16, ~10 min)

---

### SLIDE 13 — O Problema do Mean Pooling (2 min)

> "Agora vamos ao coração técnico: o **Weight-Bleeding**.
>
> O problema que a gente resolve é sutil. Quando um bi-encoder cria o embedding de um texto, ele usa **mean pooling** — simplesmente tira a MÉDIA dos embeddings de cada palavra.
>
> O problema: a média trata TODO mundo igual. Na frase 'O bi-encoder usa repetição de termos', as palavras 'O', 'de' têm o mesmo peso que 'bi-encoder' e 'repetição'. O embedding não reflete a importância real dos termos.
>
> **Exemplo concreto:** pesquisador quer que 'CBDC' e 'banco central' pesem mais que 'o', 'um', 'para'. Com mean pooling, é impossível.
>
> Isso gera dois problemas:
> **1. Scores comprimidos** — artigos tangencialmente relevantes e irrelevantes ficam com scores quase idênticos. Difícil separar.
> **2. Sem controle** — o pesquisador não consegue GUIAR a busca semanticamente."

**[Avançar]**

---

### SLIDE 14 — A Solução em 5 Passos (2.5 min)

> "A solução é elegantemente simples.
>
> **Ideia central:** se repetir um termo W vezes no texto fizesse ele contribuir W vezes mais no embedding final, podemos simular esse efeito DIRETAMENTE no espaço de embeddings — sem aumentar o texto, sem custo, sem GPU.
>
> São 5 passos:
>
> **1.** O pesquisador define num JSON os termos e pesos: CBDC=5, moeda digital=5, liquidez=2, blockchain=2.
> **2.** Cada termo vira um embedding. O sistema calcula o **centroide ponderado** — a média dos embeddings, cada um multiplicado pelo seu peso. CBDC contribui 5× mais que uma palavra normal.
> **3.** Cada artigo é comparado com esse centroide via similaridade cosseno.
> **4.** Artigos sobre CBDC sobem no ranking. Artigos sobre blockchain SEM CBDC NÃO são afetados.
> **5.** O score final passa por uma transformação de raiz quadrada — que resolve o problema dos scores comprimidos.
>
> Tudo em CPU. Milissegundos por artigo. Zero dados de treinamento."

**[Avançar]**

---

### SLIDE 15 — A Transformação Raiz Quadrada (2 min)

> "Por que a raiz quadrada é necessária? Porque em 384 dimensões, as similaridades cosseno se concentram numa faixa estreita — tipicamente entre 0.05 e 0.50. A transformação linear (score = sim × 10) não consegue separar o relevante do irrelevante.
>
> **Antes (linear):** paper relevante com sim=0.30 → score 3.0. Paper irrelevante com sim=0.25 → score 2.5. Diferença de 0.5 — quase invisível. Com threshold em 3.5, AMBOS são perdidos.
>
> **Depois (raiz quadrada):** paper relevante → √0.30 × 10 = 5.48. Irrelevante → √0.25 × 10 = 5.00. Diferença de 0.48 — bem definida. O paper relevante passa no threshold.
>
> **Impacto real:** no threshold 5.0, Weight-Bleeding + raiz quadrada aprovam **151 papers** contra **92** do baseline vanilla — **59 papers a mais** que seriam perdidos.
>
> A transformação é monotônica — preserva a ordem original. E foi escolhida entre 6 alternativas testadas."

**[Avançar]**

---

### SLIDE 16 — Resultados Experimentais (2 min)

> "Três números que comprovam o método:
>
> **96.8%** — correlação de Spearman com o bi-encoder vanilla. O ranking MUDA: 40% dos top-10 são diferentes. O peso realmente faz diferença. A correlação é alta o suficiente para não bagunçar, mas baixa o suficiente para mostrar que o efeito existe.
>
> **-0.75** — correlação NEGATIVA entre domínios SLR e Blockchain. Isso é a prova definitiva de que o efeito é ESPECÍFICO de cada domínio. Cada configuração produz um resultado ÚNICO. Não é um viés global.
>
> **7.5× mais rápido que cross-encoder** — centroide calculado em 0.5 segundos (uma vez), cada artigo em 0.01ms. O gap cresce com o volume de papers.
>
> Resultado consistente em 3 modelos: MiniLM, BGE-base, GTE-small — todos apresentam comportamento similar. O método não depende de um modelo específico."

**[Avançar — Parte 5]**

---

## PARTE 5 — CONTRIBUIÇÃO (slides 17-20, ~5 min)

---

### SLIDE 17 — vs Concorrentes (1.5 min)

> "Como o Academic Hunter se compara com as ferramentas existentes?
>
> A tabela fala por si:
>
> - **16 fontes de dados** — contra 1 das concorrentes
> - **Scoring semântico** — único com Weight-Bleeding
> - **Cluster automático, detecção de novidade, mapa da pesquisa** — ninguém mais tem
> - **API para agentes de IA via MCP** — único
> - **Custo: zero** — ASReview é grátis mas limitado, Rayyan e Covidence custam caro
>
> Academic Hunter é a única ferramenta SLR 100% gratuita, open-source, com 16 fontes, análise semântica E integração com agentes de IA."

**[Avançar]**

---

### SLIDE 18 — Posicionamento (1 min)

> "Academic Hunter ocupa uma posição ÚNICA na literatura atual:
>
> - **Survey do Singh (2025):** cataloga 7 arquiteturas de Agentic RAG — **nenhuma menciona SLR**.
> - **Queen-Bee Agents (2026):** propõe agentes especialistas conectados por MCP — **Academic Hunter é uma dessas 'abelhas'**.
> - **Mishra (2026):** identifica 'retrieval misalignment' como risco crítico em sistemas Agentic RAG — **Weight-Bleeding MITIGA esse risco** ao dar controle semântico configurável.
>
> Nenhum paper de 2025-2026 combina SLR + Weight-Bleeding + MCP."

**[Avançar]**

---

### SLIDE 19 — Publicações (1 min)

> "Dois tracks de publicação:
>
> **JOSS — Journal of Open Source Software:** foco na ferramenta, no ecossistema, em como usar. 16 conectores, 35+ ferramentas, 155 testes.
>
> **Conferência (alvo: EMNLP/ACL/ECIR):** foco no método Weight-Bleeding. 12 experimentos, 3 modelos de embedding, 5 baselines comparados.
>
> **Próximos passos:** PyPI publish, Zenodo DOI, ORCID real, validação humana com pesquisadores."

**[Avançar]**

---

### SLIDE 19 — Obrigado (1 min)

> "Bom, é isso. Academic Hunter está disponível em **github.com/devfelipenunes/academic-hunter**.
>
> **O que vocês podem fazer agora:**
>
> - **Instalar:** é um `pip install` do repositório
> - **Reportar bugs:** github issues
> - **Citar nos seus papers:** os papers JOSS e da conferência estão em andamento
> - **Contribuir:** pull requests, feedback, ideias são bem-vindos
>
> **Perguntas?**"

---

## Notas para o apresentador

### Timing

- Parte 1 (slides 1-4): ~7 min — não apressar, é onde o público decide se vai prestar atenção
- Parte 2 (slides 5-7): ~6 min — manter ritmo, MCP é o diferencial
- Parte 3 (slides 8-12): ~10 min — mais leve, cada funcionalidade tem seu próprio slide
- Parte 4 (slides 13-16): ~10 min — coração técnico, ir devagar, o slide 15 (sqrt) é o mais difícil
- Parte 5 (slides 17-21): ~5 min — fechamento rápido, deixar tempo para perguntas

### Dicas

- **Slide 3** (MCP): enfatizar que o pesquisador NÃO executa comandos — ele só pede pro Claude
- **Slide 8** (embedding SVG): apontar para outliers vermelhos no mapa
- **Slide 10** (semantic_search): mostrar o fluxo passo a passo, explicar cada etapa
- **Slide 11** (clustering): os 3 algoritmos (UMAP, HDBSCAN, c-TF-IDF) — explicar o papel de cada um
- **Slide 13** (mean pooling): usar a analogia da pesquisa de opinião
- **Slide 15** (sqrt): mostrar o antes/depois com os números — é o slide mais técnico
- **Slide 16** (resultados): cada número tem uma INTERPRETAÇÃO, não só o valor
- **Slide 20** (limitações): falar com naturalidade — mostra transparência
- **Slide 21** (CTA): terminar com entusiasmo, não com pressa

### Perguntas frequentes (preparar respostas)

1. "Precisa de GPU?" — Não. Roda em CPU, 22MB de modelo.
2. "Comparado com ChatGPT?" — AH não gera texto. Ele recupera e analisa.
3. "Dá pra usar com qualquer LLM?" — Sim, qualquer cliente MCP funciona.
4. "Vai ter UI web?" — Futuramente. Hoje é CLI interativo ou MCP.
5. "Já publicaram?" — JOSS submetido, conference paper em preparação.
