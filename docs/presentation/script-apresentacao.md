# Script de Apresentação — Academic Hunter

**Duração:** ~35 minutos (19 slides)
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

## PARTE 2 — O SOFTWARE (slides 5-7, ~6 min)

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

## PARTE 3 — FUNCIONALIDADES MINILM (slides 8-12, ~9 min)

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

### SLIDE 10 — Search + Clusters (2 min)

> "Vou mostrar duas funcionalidades em detalhe.
>
> **Primeiro: busca semântica.** Reparem no exemplo. A pergunta é: 'CBDC impact on bank disintermediation'. Nenhum dos três resultados contém a palavra 'disintermediation' — mas o sistema entendeu o conceito e trouxe artigos relevantes.
>
> Isso é a diferença entre buscar por PALAVRAS e buscar por CONCEITOS.
>
> **Segundo: clusters automáticos.** Numa base de 50 papers, o sistema descobriu 3 clusters:
>
> - 'literature, systematic, review' — 23 papers sobre revisão sistemática
> - 'topic, sentence, embedding' — 15 papers sobre embeddings
> - E um outlier: detecção de anomalia em grafos com GNNs
>
> Isso é **taxonomia automática** — você não precisa definir as categorias antes. O sistema descobre."

**[Avançar]**

---

### SLIDE 11 — Novidade + Evolução + Mapa (2 min)

> "Três funcionalidades que ajudam o pesquisador a enxergar o que NÃO está óbvio.
>
> **1. Radar de novidade:** detecta artigos que não se encaixam em nenhum cluster. Esses são frequentemente os mais interessantes — pesquisa interdisciplinar, tendências emergentes. Nos nossos testes, encontramos dois: um sobre detecção de anomalia em GNNs e outro sobre análise de contratos Ethereum.
>
> **2. Evolução temporal:** aqui com DADOS REAIS da nossa base. De 2020 a 2025, o número de papers cresceu de 3 para 12 — um crescimento de 4x em 5 anos. Isso mostra que a área está QUENTE.
>
> **3. Mapa 2D:** 100 papers projetados em 2D. CBDC, IA/ML, outliers — tudo visível num golpe de olho."

**[Avançar]**

---

### SLIDE 12 — Precisão + Resumo + Dedup (1.5 min)

> "Três funcionalidades de precisão e qualidade:
>
> **Re-ranqueamento:** duas etapas. O MiniLM busca rápido os top-20, depois um cross-encoder re-rank os top-5 com mais precisão. Ganho de +9 pontos de precisão.
>
> **Resumo automático:** dado um DOI, o sistema extrai as 3 sentenças mais representativas do abstract. Ele seleciona sentenças que são relevantes ao tema E não redundantes entre si — isso é o algoritmo MMR.
>
> **Dedup semântico:** detecta duplicatas que o DOI não pega. Um preprint e sua versão publicada têm DOIs diferentes, mas embeddings similares — o sistema agrupa automaticamente."

**[Avançar — Parte 4]**

---

## PARTE 4 — WEIGHT-BLEEDING (slides 13-15, ~7 min)

---

### SLIDE 13 — O Problema (2 min)

> "Agora vamos ao coração técnico: o **Weight-Bleeding**.
>
> O problema que a gente resolve é sutil, mas importante. Quando um bi-encoder cria o embedding de um texto, ele usa **mean pooling** — tira a média de todas as palavras. O problema é que a média trata TODO mundo igual.
>
> **A analogia é uma pesquisa de opinião:** mean pooling é como dar 1 voto para cada pessoa — inclusive para quem não entende do assunto.
>
> Um pesquisador sobre CBDC quer que 'banco central' e 'moeda digital' tenham MAIS PESO que 'o', 'um', 'para'.
>
> Isso gera dois problemas práticos:
>
> 1. **Scores comprimidos** — artigos parecidos mas não exatos ficam com scores muito próximos, difícil separar o relevante do irrelevante.
> 2. **Sem controle** — o pesquisador não consegue 'guiar' a busca."

**[Avançar]**

---

### SLIDE 14 — A Solução (2.5 min)

> "A solução é elegantemente simples.
>
> **Ideia central:** se repetir um termo no texto fizesse ele contribuir mais, por que não fazer isso diretamente no espaço de embeddings? É matematicamente equivalente — mas sem aumentar o texto, sem custo extra, sem precisar de GPU.
>
> Na prática:
>
> **1.** O pesquisador define num JSON os termos importantes e seus pesos. Por exemplo: 'CBDC' com peso 5.0, 'moeda digital' com 5.0, 'liquidez' com 2.0, 'blockchain' com 2.0.
>
> **2.** O sistema calcula um **centroide ponderado** — uma 'posição alvo' no espaço de embeddings que reflete esses pesos.
>
> **3.** Cada artigo é comparado com esse centroide. Quanto mais próximo, mais relevante. Artigos sobre blockchain SEM CBDC não são afetados — o controle é preciso.
>
> Tudo em CPU, milissegundos por artigo, zero dados de treinamento."

**[Avançar]**

---

### SLIDE 15 — Resultados (2 min)

> "E os resultados comprovam que funciona:
>
> **96.8% de correlação com vanilla** — o ranking MUDA em relação ao método padrão. 40% dos top-10 são diferentes. O peso realmente faz diferença.
>
> **-0.75 de correlação entre domínios** — correlação NEGATIVA entre configurações de SLR e Blockchain. Isso prova que o efeito é ESPECÍFICO de cada domínio. Cada configuração produz um resultado único.
>
> **7.5× mais rápido que cross-encoder** — o centroide é calculado em 0.5 segundos, cada artigo é milissegundos. Resultado consistente em 3 modelos de embedding diferentes.
>
> Na prática: **59 artigos a mais** são aprovados com Weight-Bleeding contra o método tradicional. Papers que seriam perdidos são resgatados."

**[Avançar — Parte 5]**

---

## PARTE 5 — CONTRIBUIÇÃO (slides 16-19, ~5 min)

---

### SLIDE 16 — vs Concorrentes (1.5 min)

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

### SLIDE 17 — Posicionamento (1 min)

> "Academic Hunter ocupa uma posição ÚNICA na literatura atual:
>
> - **Survey do Singh (2025):** cataloga 7 arquiteturas de Agentic RAG — **nenhuma menciona SLR**.
> - **Queen-Bee Agents (2026):** propõe agentes especialistas conectados por MCP — **Academic Hunter é uma dessas 'abelhas'**.
> - **Mishra (2026):** identifica 'retrieval misalignment' como risco crítico em sistemas Agentic RAG — **Weight-Bleeding MITIGA esse risco** ao dar controle semântico configurável.
>
> Nenhum paper de 2025-2026 combina SLR + Weight-Bleeding + MCP."

**[Avançar]**

---

### SLIDE 18 — Publicações (1 min)

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
- Parte 3 (slides 8-12): ~9 min — parte mais densa, pausar para perguntas se necessário
- Parte 4 (slides 13-15): ~7 min — coração técnico, ir devagar
- Parte 5 (slides 16-19): ~5 min — fechamento rápido, deixar tempo para perguntas

### Dicas

- **Slide 3** (MCP): enfatizar que o pesquisador NÃO executa comandos — ele só pede pro Claude. O foco é a ORQUESTRAÇÃO via MCP
- **Slide 8** (embedding SVG): apontar para outliers vermelhos no mapa
- **Slide 9** (12× MiniLM): fazer pausa dramática antes do callout final
- **Slide 14** (solução): não mostrar a fórmula — a analogia é suficiente
- **Slide 18** (limitações): falar com naturalidade — mostra transparência
- **Slide 19** (CTA): terminar com entusiasmo, não com pressa

### Perguntas frequentes (preparar respostas)

1. "Precisa de GPU?" — Não. Roda em CPU, 22MB de modelo.
2. "Comparado com ChatGPT?" — AH não gera texto. Ele recupera e analisa.
3. "Dá pra usar com qualquer LLM?" — Sim, qualquer cliente MCP funciona.
4. "Vai ter UI web?" — Futuramente. Hoje é CLI interativo ou MCP.
5. "Já publicaram?" — JOSS submetido, conference paper em preparação.
