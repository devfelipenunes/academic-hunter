# Script de Apresentação — Academic Hunter

**Duração:** ~40 minutos (20 slides)
**Público:** Pesquisadores (não especialistas em IA)
**Tom:** Conversacional, entusiasmado, constrói ideias do zero

---

## PARTE 1 — O PROBLEMA (slides 1-3, ~5 min)

---

### SLIDE 1 — Título (1 min)

> "Bom dia. Eu queria começar com uma provocação:
>
> **Quanto tempo leva uma Revisão Sistemática da Literatura hoje?**
>
> Seis. A. Doze. Meses. E não é por falta de ferramentas — é porque as ferramentas que existem resolvem metade do problema.
>
> Hoje eu vou mostrar uma plataforma que a gente construiu chamada **Academic Hunter**. Ela reduz esse tempo de **6 a 12 meses para 15 minutos**. Não substituindo o pesquisador — automatizando o trabalho braçal de busca, triagem e análise inicial.
>
> Tudo open source, gratuito, roda em qualquer notebook. Sem GPU, sem API paga."

**[Avançar]**

---

### SLIDE 2 — O Problema (2 min)

> "Vamos entender por que leva tanto tempo.
>
> **6 a 12 meses.** Parece loucura, mas é real. E por quê? Porque as ferramentas que existem obrigam você a escolher entre:
>
> **1. Keyword matching** — que perde sinônimos. Você busca 'CBDC' e o artigo fala 'moeda digital do banco central'. Perdeu. Num universo de 10, 20 mil artigos, isso é inaceitável.
>
> **2. Rotular dados manualmente** — o ASReview exige que você classifique dezenas de papers manualmente antes de começar a funcionar. É como pedir pra você fazer metade do trabalho pra ferramenta começar a te ajudar.
>
> **3. Pagos e fechados** — Rayyan e Covidence custam de 100 a 500 dólares POR MÊS. São cloud. Não têm API. Você não integra com nada.
>
> **4. Dependem de GPU** — modelos de IA precisam de placa de vídeo de mil dólares+. Setup complexo, custo alto.
>
> **Academic Hunter resolve todos esses problemas — de graça, numa máquina comum, e melhor."**

**[Avançar]**

---

### SLIDE 3 — O Fluxo (1.5 min)

> "Antes de eu mostrar as funcionalidades, quero que vocês tenham na cabeça o fluxo completo. São 4 etapas:
>
> **1. Configurar** — você só diz o tópico. O sistema descobre os jargões automaticamente.
> **2. Buscar** — 7 bases acadêmicas em paralelo (15 no total). Milhares de artigos em minutos.
> **3. Analisar** — 12 análises automáticas usando IA. É aqui que a mágica acontece.
> **4. Exportar** — CSV, BibTeX, RIS, JSON, Markdown, Obsidian. O formato que você precisar.
>
> E o mais importante: cada uma dessas análises pode ser chamada por um agente de IA automaticamente. E é sobre isso que eu vou falar agora."

**[Avançar — Parte 2]**

---

## PARTE 2 — O DIFERENCIAL (slides 4-8, ~8 min)

---

### SLIDE 4 — Integração com IA (MCP) (2 min)

> "O que faz o Academic Hunter ser diferente de qualquer outra ferramenta SLR?
>
> A gente implementou um padrão chamado **MCP — Model Context Protocol**. Vou explicar o que é.
>
> Sabe quando você usa o ChatGPT ou o Claude e ele não consegue acessar informações de fora? Ele só sabe o que foi treinado. O MCP resolve isso: é um **protocolo aberto** que permite que QUALQUER agente de IA se conecte a ferramentas externas.
>
> Foi criado pela Anthropic, mas hoje é mantido pela Linux Foundation — o mesmo pessoal do Linux, do Kubernetes. OpenAI e Google adotaram.
>
> O Academic Hunter expõe **44 ferramentas, 3 recursos, 1 template e 2 prompts** via MCP. Na prática: um agente de IA pode chamar cada funcionalidade que eu vou mostrar automaticamente.
>
> É como ter um **assistente de pesquisa** que sabe usar TODAS as ferramentas e planeja sozinho a melhor sequência de passos."

**[Avançar]**

---

### SLIDE 5 — MCP em Ação (2 min)

> "Vou mostrar como funciona na prática.
>
> O pesquisador abre o Claude — ou qualquer agente compatível com MCP — e simplesmente PEDE:
>
> _'Faça uma revisão sobre o impacto de CBDCs na estabilidade financeira.'_
>
> O Claude então planeia e executa cada etapa:
>
> **1.** Descobre os jargões da área automaticamente.
> **2.** Busca artigos por CONCEITO — não por palavra exata.
> **3.** Agrupa os resultados por tema automaticamente.
> **4.** Detecta artigos fora do padrão — pesquisa disruptiva.
> **5.** Gera um mapa 2D interativo da produção científica.
> **6.** Salva tudo no Obsidian — o Second Brain do pesquisador.
>
> **O pesquisador valida o resultado em 15 minutos. Não em 6 meses.**
>
> O Claude orquestra 44 ferramentas especializadas. O pesquisador só valida o trabalho."

**[Avançar]**

---

### SLIDE 6 — 16 Fontes (1.5 min)

> "Mas o Academic Hunter não é só integração com IA. A base dele é sólida.
>
> **7 fontes acadêmicas em paralelo** — uma das maiores coberturas entre ferramentas SLR. O pipeline consulta automaticamente:
>
> Bases tradicionais como arXiv, Crossref e DOAJ. APIs inteligentes como Semantic Scholar, OpenAlex, CORE e DBLP.
>
> Outras 8 ficam disponíveis sob demanda pelas tools MCP: Europe PMC, OpenCitations (2 bilhões de links de citação), Unpaywall (acesso aberto), Lens.org (patentes), OpenAIRE (3.7 milhões de projetos financiados), bioRxiv, medRxiv e DataCite.
>
> Tudo em paralelo, com limite de taxa inteligente pra não sobrecarregar as APIs."

**[Avançar]**

---

### SLIDE 7 — Posicionamento (1.5 min)

> "Importante: o que o Academic Hunter É e o que ele NÃO é.
>
> ❌ **Não é um ChatGPT.** Ele não gera texto, não inventa respostas, não alucina. Ele RECUPERA e ANALISA o que já foi publicado.
>
> ❌ **Não é um agente autônomo.** Ele é uma caixa de ferramentas especializadas. Quem decide o que fazer é o agente IA — ou você.
>
> ✅ **É um motor de busca semântica.** Entende o SIGNIFICADO, não só as palavras.
>
> ✅ **É a 'parte inteligente' de um sistema maior.** Na literatura, isso se chama Agentic RAG — um agente IA orquestra; o Academic Hunter executa a parte especializada."

**[Avançar]**

---

### SLIDE 8 — Arquitetura (1.5 min)

> "Como tudo isso se conecta? Arquitetura hexagonal baseada em plugins.
>
> Quatro camadas:
>
> **MCP Server** — a interface com agentes de IA. 44 ferramentas.
> **Core Domain** — o núcleo. O modelo de paper, o scoring, o pipeline, a exportação PRISMA. TUDO funciona sem LLM.
> **Plugin Layer** — cada fonte de dados é um plugin independente. Quer adicionar uma nova base? Não precisa mexer no núcleo.
> **Infrastructure** — SQLite pra cache, ChromaDB pros vetores, config JSON.
>
> Isso permite escalar horizontalmente sem nunca reescrever o núcleo."

**[Avançar — Parte 3]**

---

## PARTE 3 — COMO FUNCIONA (slides 9-13, ~10 min)

---

### SLIDE 9 — Embeddings (2.5 min)

> "Agora que vocês já entenderam o que a ferramenta faz e por que ela é diferente, vou explicar COMO ela entende textos.
>
> O conceito fundamental é **embedding**.
>
> Embedding é uma **impressão digital matemática** de um texto. Cada artigo vira um vetor de **384 números**. Pode parecer abstrato, mas a ideia é simples: artigos sobre temas parecidos geram VETORES parecidos — eles ficam PRÓXIMOS uns dos outros num espaço multidimensional.
>
> **A melhor analogia é um mapa da cidade.** Imaginem que cada artigo é um ponto no mapa. Artigos sobre inteligência artificial ficam no 'bairro' da IA. Blockchain fica noutro bairro. Quanto mais distante um tema do outro, maior a distância entre eles no mapa.
>
> **Aqui no slide vocês estão vendo dados REAIS** — 100 papers do Academic Hunter projetados em 2D. Os pontos verdes são papers sobre CBDC, os azuis são IA/ML, os vermelhos são outliers — papers que não se encaixam em lugar nenhum.
>
> E o modelo que faz tudo isso? **22 megabytes.** Cabe num arquivo menor que uma foto JPEG. Roda em QUALQUER computador — sem GPU, sem nuvem, sem custo."

**[Avançar]**

---

### SLIDE 10 — 12× MiniLM (1.5 min)

> "O mais impressionante: o **mesmo modelo de 22MB** — chamado all-MiniLM-L6-v2 — alimenta **12 funcionalidades diferentes**.
>
> **Scoring:** ranqueamento inteligente dos artigos por relevância.
> **Search:** busca por conceito, re-ranqueamento com precisão, e snowballing.
> **Analysis:** clustering temático, detecção de outliers, evolução temporal, mapa 2D, sumarização automática, dedup semântico.
>
> **Um modelo. 22MB. CPU. Zero API paga. Doze funcionalidades.**
>
> Nenhuma outra ferramenta SLR chega perto disso."

**[Avançar]**

---

### SLIDE 11 — Busca Semântica (2 min)

> "Vou mostrar duas funcionalidades em detalhe. Primeiro: **semantic_search**.
>
> O passo a passo é simples. Quando o pesquisador faz uma pergunta:
>
> A pergunta vira um embedding — 384 números que capturam o significado.
> Esse embedding é comparado com todos os 7.338 papers indexados usando **similaridade cosseno** — basicamente, mede o ângulo entre os vetores.
> Os top-3 mais similares são retornados.
>
> **Exemplo real.** A pergunta foi: 'CBDC impact on bank disintermediation'.
>
> Olhem os resultados: 'Retail CBDC: Implications for Banking', 'CBDC and Financial Stability', 'The Optimal Quantity of CBDC'.
>
> **Nenhum desses títulos contém a palavra 'disintermediation'.** Mas o sistema entendeu o CONCEITO e trouxe artigos relevantes.
>
> Essa é a diferença entre buscar por PALAVRAS e buscar por SIGNIFICADO."

**[Avançar]**

---

### SLIDE 12 — Clusters (2 min)

> "Segunda funcionalidade: **cluster_papers**.
>
> Lembram do mapa da cidade? O cluster_papers faz algo parecido: ele agrupa automaticamente milhares de artigos por assunto, sem você precisar definir categorias antes.
>
> O algoritmo BERTopic funciona em 3 etapas:
>
> **1. UMAP** — pega os 384 números de cada artigo e reduz pra um espaço menor, preservando as distâncias entre eles.
> **2. HDBSCAN** — agrupa os pontos por densidade. Diferente de outros métodos, ele NÃO precisa que você diga quantos clusters existem. Ele descobre sozinho.
> **3. c-TF-IDF** — para cada grupo, ele extrai as palavras mais importantes e dá nome ao tema automaticamente.
>
> **Exemplo real com dados da nossa base:** 50 papers processados, 3 clusters encontrados:
>
> Cluster 1: 'literature, systematic, review' — 23 papers sobre Revisão Sistemática
> Cluster 2: 'topic, sentence, embedding' — 15 papers sobre Embeddings
> Cluster 3: 'search, ai, intelligent' — 12 papers sobre IA
>
> E **2 outliers** — papers que não se encaixam: um sobre detecção de anomalia em GNNs, outro sobre contratos Ethereum.
>
> Isso é **taxonomia automática**. O sistema descobre a estrutura do seu campo sozinho."

**[Avançar]**

---

### SLIDE 13 — Mais Funcionalidades (1.5 min)

> "Rapidamente, outras funcionalidades:
>
> **Detecção de novidade:** algoritmos estatísticos identificam papers que fogem do padrão — frequentemente os mais interessantes. Pesquisa disruptiva, interdisciplinar, tendências emergentes.
>
> **Evolução temporal:** com dados REAIS da nossa base. De 2020 a 2025, o número de papers cresceu de 3 para 12 — um crescimento de 4x. Isso mostra que a área está QUENTE.
>
> **Resumo, dedup e re-rank:** o summarize_paper extrai as 3 sentenças mais relevantes de um abstract usando o algoritmo MMR. O semantic_dedup agrupa duplicatas que o DOI não pega. O rerank_search combina rapidez do MiniLM com precisão do cross-encoder."

**[Avançar — Parte 4]**

---

## PARTE 4 — O MÉTODO (slides 14-17, ~10 min)

---

### SLIDE 14 — Mean Pooling (2.5 min)

> "Agora vamos ao coração técnico: **Weight-Bleeding**.
>
> Pra entender o problema que ele resolve, primeiro precisa entender como um bi-encoder cria embeddings.
>
> Quando o modelo processa um texto, ele transforma cada palavra num embedding e depois tira a **média simples de todas elas**. Isso se chama **mean pooling**.
>
> O problema: a média trata TODO mundo igual. Na frase 'O bi-encoder usa repetição de termos', as palavras 'O', 'usa', 'de' têm o MESMO peso que 'bi-encoder' e 'repetição'.
>
> **É como uma pesquisa de opinião onde todo mundo tem UM voto — inclusive quem não entende do assunto.**
>
> Um pesquisador sobre CBDC quer que 'banco central' e 'moeda digital' tenham MAIS PESO que 'o', 'um', 'para'. Mas o modelo não permite.
>
> **Consequências:**
>
> 1. **Scores comprimidos** — artigos parecidos mas não exatos ficam com scores quase idênticos. Impossível separar o relevante do irrelevante.
> 2. **Sem controle** — o pesquisador não consegue 'guiar' a busca, dizer que certos termos são mais importantes."

**[Avançar]**

---

### SLIDE 15 — Solução em 5 Passos (2.5 min)

> "A solução é elegantemente simples.
>
> **Ideia central:** se repetir um termo no texto fizesse ele contribuir mais vezes no embedding final, podemos simular esse efeito DIRETAMENTE no espaço de embeddings — sem aumentar o texto, sem custo, sem GPU.
>
> São 5 passos:
>
> **Passo 1:** o pesquisador define num arquivo JSON os termos importantes e seus pesos. Exemplo: 'CBDC' com peso 5, 'moeda digital' com 5, 'liquidez' com 2, 'blockchain' com 2. Quanto maior o peso, mais aquele termo puxa o resultado.
>
> **Passo 2:** cada termo vira um embedding. O sistema calcula um **centroide ponderado** — basicamente a média dos embeddings, mas cada um multiplicado pelo seu peso. 'CBDC' com peso 5 contribui CINCO VEZES mais que uma palavra normal.
>
> **Passo 3:** cada artigo é comparado com esse centroide via similaridade cosseno.
>
> **Passo 4:** artigos sobre CBDC SOBEM no ranking. Artigos sobre blockchain SEM CBDC NÃO são afetados. O controle é preciso.
>
> **Passo 5:** o score final passa por uma transformação de raiz quadrada — que resolve o problema dos scores comprimidos.
>
> Tudo em CPU, milissegundos por artigo, zero dados de treinamento."

**[Avançar]**

---

### SLIDE 16 — Raiz Quadrada (2.5 min)

> "Por que a raiz quadrada é necessária? Vou mostrar com números.
>
> Em 384 dimensões, as similaridades cosseno se concentram numa faixa muito estreita — tipicamente entre 0.05 e 0.50. Isso significa que um paper razoavelmente relevante e um irrelevante podem ter scores quase idênticos.
>
> **Antes, com transformação linear:**
> Paper relevante com similaridade 0.30 → score 3.0
> Paper irrelevante com similaridade 0.25 → score 2.5
> Diferença: 0.5 — quase invisível. Com um threshold de 3.5, AMBOS são perdidos.
>
> **Depois, com raiz quadrada:**
> Paper relevante → √0.30 × 10 = 5.48
> Paper irrelevante → √0.25 × 10 = 5.00
> Diferença: 0.48 — bem definida. O paper relevante passa no threshold.
>
> **Impacto real:** no threshold 5.0, Weight-Bleeding + raiz quadrada aprovam **151 papers** contra **92** do método tradicional. **59 papers a mais** que seriam perdidos são resgatados.
>
> E a ordenação original é preservada — a raiz quadrada é monotônica, não bagunça o ranking."

**[Avançar]**

---

### SLIDE 17 — Resultados (2 min)

> "Três números que resumem a validação:
>
> **96.8%** — é a correlação de Spearman com o bi-encoder vanilla. Isso significa que o ranking MUDA — 40% dos top-10 são diferentes. O peso faz diferença real. Mas a correlação é alta o suficiente pra não bagunçar o resultado.
>
> **-0.75** — correlação NEGATIVA entre domínios. A gente configurou o sistema pra SLR e pra Blockchain. Os rankings produziram correlação negativa. Isso PROVA que o efeito não é um viés global — cada configuração produz um resultado ÚNICO e específico praquele domínio.
>
> **7.5× mais rápido que cross-encoder** — o centroide é calculado em 0.5 segundos, cada artigo leva 0.01ms. O gap cresce com o volume de papers. E o resultado é consistente em 3 modelos diferentes: MiniLM, BGE-base e GTE-small."

> **[Proveniência]** Os quatro números deste slide foram medidos. Os artefatos saíram deste
> repositório junto com `papers/` em `6a48f1c`, e continuam recuperáveis pelo histórico do
> git: o 96.8% e o −0.75 estão em `additional_experiments.json` (`0.9681` e `−0.7463`), e os
> três ρ por modelo em `benchmark_results.txt`. Uma ressalva sobre o −0.75: o script que o
> imprimia procurava a chave `spearman_rho`, que não existe no arquivo (a real é
> `slr_vs_bc_wb_spearman`), então ele saiu de um _default_ que por acaso arredonda o valor
> medido — certo pelo motivo errado.

**[Avançar — Parte 5]**

---

## PARTE 5 — CONTRIBUIÇÃO (slides 18-20, ~4 min)

---

### SLIDE 18 — vs Concorrentes (1.5 min)

> "Como o Academic Hunter se compara?
>
> **7 fontes em paralelo** (15 no total) — contra 1 das concorrentes.
> **Scoring semântico, clusters, detecção de novidade, mapa da pesquisa** — ninguém mais tem.
> **API para agentes de IA via MCP** — único.
> **Custo:** zero. ASReview é grátis mas limitado. Rayyan e Covidence custam caro.
>
> Academic Hunter é a única ferramenta SLR 100% gratuita, open-source, com análise semântica E integração com agentes de IA."

**[Avançar]**

---

### SLIDE 19 — Posicionamento (1 min)

> "Academic Hunter ocupa uma posição única na literatura atual.
>
> O survey do Singh (2025) cataloga 7 arquiteturas de Agentic RAG — nenhuma menciona SLR.
>
> O Queen-Bee Agents (2026) propõe agentes especialistas conectados por MCP — Academic Hunter é exatamente isso: uma 'abelha' especializada em SLR.
>
> O Mishra (2026) identifica o 'retrieval misalignment' como risco crítico — quando a recuperação de informação não reflete as prioridades da tarefa. O Weight-Bleeding MITIGA esse risco ao dar controle semântico configurável.
>
> Nenhum paper de 2025-2026 combina SLR + Weight-Bleeding + MCP. É uma posição única."

**[Avançar]**

---

### SLIDE 20 — Publicações + CTA (1.5 min)

> "Dois tracks de publicação:
>
> **JOSS** — Journal of Open Source Software — foco na ferramenta, no ecossistema, em como usar. 15 fontes, 44 ferramentas, 993 testes.
>
> **Conferência** — alvo EMNLP/ACL/ECIR — foco no método Weight-Bleeding. 12 experimentos, 3 modelos, 5 baselines.
>
> **O que vocês podem fazer:**
>
> - Instalar: `pip install git+https://github.com/devfelipenunes/academic-hunter.git`
> - Testar, reportar bugs, contribuir
> - Citar nos seus papers — os dois estão em preparação
>
> **Perguntas?**"

---

## Notas para o apresentador

### Timing

- Parte 1 (1-3): ~5 min — direto, sem rodeios
- Parte 2 (4-8): ~8 min — MCP é o gancho, gastar tempo, mostrar entusiasmo
- Parte 3 (9-13): ~10 min — embeddings é o conceito mais importante, ir devagar
- Parte 4 (14-17): ~10 min — slide 16 (sqrt) merece calma
- Parte 5 (18-20): ~4 min — fechamento rápido

### Dicas importantes

- **Slide 4** (MCP): primeira vez que o termo aparece. Dizer claramente "MCP é um protocolo que permite IAs usarem ferramentas"
- **Slide 5** (diálogo): o melhor slide pra vender a ferramenta. Mostrar empolgação
- **Slide 9** (embeddings): a analogia do mapa é essencial. SEM MAPA O CONCEITO NÃO FICA CLARO
- **Slide 14** (mean pooling): usar a analogia da pesquisa de opinião
- **Slide 16** (sqrt): mostrar os números devagar, um de cada vez
- **Slide 19** (posicionamento): falar com segurança — mostra domínio da literatura
- **Slide 20** (CTA): terminar com energia, não com pressa

### Glossário rápido pra perguntas

- **Embedding:** vetor de números que representa o significado de um texto
- **MCP:** protocolo que permite IAs acessarem ferramentas externas
- **RAG:** recuperar informação antes de gerar resposta
- **Agentic RAG:** agente IA que planeja múltiplas recuperações
- **Bi-encoder:** modelo que transforma texto em vetor
- **Cross-encoder:** modelo mais preciso que compara dois textos diretamente
