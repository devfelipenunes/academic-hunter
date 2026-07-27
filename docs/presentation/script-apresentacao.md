# Script de Apresentação — Academic Hunter

**Duração:** ~42 minutos (22 slides)
**Público:** Pesquisadores (não necessariamente especialistas em IA)
**Tom:** Conceitual, constrói conhecimento passo a passo, sem jargão técnico não explicado

---

## PARTE 1 — O QUE É O ACADEMIC HUNTER (slides 1-4, ~7 min)

---

### SLIDE 1 — Título (1 min)

> "Bom dia. Hoje vou apresentar o **Academic Hunter**, uma plataforma aberta de Revisão Sistemática da Literatura.
>
> A gente reduz o tempo de uma SLR de **6 a 12 meses** para **15 minutos** — não substituindo o pesquisador, mas automatizando o trabalho braçal de busca, triagem e análise inicial.
>
> Tudo open source, gratuito, e roda em qualquer notebook — sem GPU, sem API paga."

**[Avançar]**

---

### SLIDE 2 — O Problema (2 min)

> "Por que uma SLR leva tanto tempo? Porque as ferramentas que existem obrigam você a escolher entre:
>
> - **Keyword matching** — que perde sinônimos. Se você busca 'CBDC' e o artigo fala 'moeda digital do banco central', você perde o artigo. Num mundo com dezenas de milhares de artigos, isso é inaceitável.
> - **Rotular dados manualmente** — o ASReview exige que você classifique dezenas de papers antes de começar a funcionar.
> - **Pagos e fechados** — Rayyan e Covidence custam de 100 a 500 dólares POR MÊS, são cloud, e não têm API para integrar com IA.
> - **Dependem de GPU** — modelos de IA precisam de placa de vídeo cara.
>
> **Academic Hunter resolve todos esses problemas — de graça, e melhor.**

**[Avançar]**

---

### SLIDE 3 — O Fluxo em 4 Etapas (1.5 min)

> "Antes de mostrar as funcionalidades, quero que vocês entendam o fluxo completo. São 4 etapas:
>
> **1. Configurar** — o pesquisador diz qual é o tópico. O sistema descobre os jargões automaticamente.
> **2. Buscar** — 16 bases acadêmicas em paralelo. Milhares de artigos em minutos.
> **3. Analisar** — 12 análises automáticas usando IA.
> **4. Exportar** — CSV, BibTeX, RIS, JSON, Markdown, PRISMA, Obsidian.
>
> O mais importante: cada análise pode ser chamada por um agente de IA. Mas vamos chegar lá."

**[Avançar]**

---

### SLIDE 4 — 16 Fontes Acadêmicas (1.5 min)

> "Primeira etapa: a busca. O Academic Hunter se conecta a **16 fontes simultaneamente** — a maior cobertura entre ferramentas SLR.
>
> Temos bases tradicionais (arXiv, Crossref, Europe PMC), APIs inteligentes (Semantic Scholar, OpenAlex), preprints (bioRxiv, medRxiv), dados de citação (OpenCitations), acesso aberto (Unpaywall), patentes (Lens.org), grants (OpenAIRE), dados de pesquisa (DataCite) e identificadores de autores (ORCID).
>
> Tudo em paralelo, com limite de taxa inteligente."

**[Avançar — Parte 2]**

---

## PARTE 2 — COMO O SISTEMA ENTENDE TEXTOS (slides 5-9, ~10 min)

---

### SLIDE 5 — Embeddings: a "impressão digital" dos textos (2 min)

> "Para entender as análises, primeiro precisa entender um conceito: **embeddings**.
>
> Embedding é uma **impressão digital matemática** de um texto. Cada artigo vira um vetor de **384 números**. Artigos sobre temas parecidos geram vetores parecidos — ficam próximos uns dos outros.
>
> A analogia é um **mapa da cidade**: artigos sobre IA ficam no 'bairro' da inteligência artificial. Blockchain fica noutro bairro. A distância entre eles reflete a distância entre os assuntos.
>
> **Aqui no slide, vocês estão vendo dados REAIS** — 100 papers do Academic Hunter projetados em 2D. Os pontos verdes são papers sobre CBDC, os azuis são IA/ML, os vermelhos são outliers — papers que não se encaixam em lugar nenhum.
>
> E o modelo que faz tudo isso cabe num arquivo de **22 megabytes** — menor que uma foto JPEG. Roda em QUALQUER computador."

**[Avançar]**

---

### SLIDE 6 — 12× MiniLM: Um Modelo, 12 Funções (1.5 min)

> "E aqui está o fato mais impressionante: **o mesmo modelo de 22MB alimenta 12 funcionalidades diferentes**.
>
> **Scoring:** ranqueamento inteligente dos artigos.
> **Search:** busca por conceito, re-ranqueamento com precisão, e snowballing.
> **Analysis:** clustering temático, detecção de outliers, evolução temporal, mapa 2D, sumarização automática, e mais.
>
> Tudo do mesmo modelo. Zero GPU. Zero API paga. Nenhuma outra ferramenta SLR faz isso."

**[Avançar]**

---

### SLIDE 7 — Busca Semântica (2 min)

> "Vamos ver a primeira funcionalidade em detalhe: **semantic_search**.
>
> O slide mostra o passo a passo. Quando o pesquisador faz uma pergunta, o sistema:
>
> **1.** Transforma a pergunta num embedding — 384 números que representam o significado.
> **2.** Compara esse embedding com os 7.338 papers indexados usando **similaridade cosseno** — basicamente, mede o ângulo entre os vetores.
> **3.** Retorna os mais similares.
>
> Exemplo real: a pergunta é 'CBDC impact on bank disintermediation'. A palavra 'disintermediation' NÃO aparece em nenhum resultado — mas o sistema entendeu o CONCEITO e trouxe artigos relevantes como 'Retail CBDC: Implications for Banking'.
>
> Isso é a diferença entre buscar por PALAVRAS e buscar por SIGNIFICADO."

**[Avançar]**

---

### SLIDE 8 — Clusters Automáticos (2 min)

> "Segunda funcionalidade: **cluster_papers**.
>
> O algoritmo BERTopic funciona em 3 etapas:
>
> **1. UMAP** — reduz as 384 dimensões para um espaço menor, preservando as distâncias entre os papers.
> **2. HDBSCAN** — agrupa os pontos por densidade. Diferente do K-means, ele NÃO precisa que você diga quantos clusters existem.
> **3. c-TF-IDF** — para cada cluster, extrai as palavras mais importantes. Isso dá nome aos temas automaticamente.
>
> Exemplo real: 50 papers → 3 clusters (Revisão Sistemática, Embeddings, IA) + 2 outliers (GNNs, Ethereum). O sistema descobriu a estrutura do campo sozinho."

**[Avançar]**

---

### SLIDE 9 — Novidade, Evolução e Síntese (2 min)

> "Demais funcionalidades:
>
> **Detecção de novidade:** algoritmos estatísticos identificam papers que fogem do padrão — frequentemente os mais interessantes.
>
> **Evolução temporal:** dados REAIS: de 3 papers em 2020 para 12 em 2025 — crescimento de 4x.
>
> **Resumo, dedup e re-rank:** o summarize_paper extrai as sentenças mais relevantes de um abstract. O semantic_dedup agrupa duplicatas que o DOI não pega. O rerank_search combina rapidez com precisão."

**[Avançar — Parte 3]**

---

## PARTE 3 — INTEGRAÇÃO COM IA (slides 10-13, ~7 min)

---

### SLIDE 10 — Integração com Agentes de IA (2 min)

> "Agora vamos falar sobre um diferencial importante do Academic Hunter: a integração com agentes de IA como Claude e ChatGPT.
>
> O Academic Hunter implementa um padrão chamado **MCP — Model Context Protocol**. É um protocolo aberto, criado pela Anthropic e adotado pela Linux Foundation, OpenAI e Google. Ele permite que QUALQUER agente de IA se conecte a ferramentas externas de forma padronizada.
>
> O Academic Hunter expõe **35+ ferramentas, 4 recursos e 2 templates** via MCP. Isso significa que um agente de IA pode chamar cada funcionalidade que mostramos automaticamente.
>
> É como ter um assistente de pesquisa que sabe usar todas as ferramentas do Academic Hunter — e planeja sozinho a melhor sequência de passos para cada tarefa."

**[Avançar]**

---

### SLIDE 11 — MCP em Ação (2 min)

> "Na prática, funciona assim:
>
> O pesquisador simplesmente PEDE pro Claude: 'Faça uma revisão sobre o impacto de CBDCs na estabilidade financeira'.
>
> O Claude planeia e executa cada etapa via MCP:
>
> 1. **quick_topic_discovery** — descobre os jargões da área
> 2. **semantic_search** — busca artigos por conceito
> 3. **cluster_papers** — agrupa os resultados por tema
> 4. **find_novel_papers** — detecta artigos fora do padrão
> 5. **visualize_landscape** — gera o mapa 2D
> 6. **export_to_obsidian** — salva no Second Brain
>
> Resultado: o pesquisador valida o trabalho em **15 minutos**, não em 6 meses.
>
> **O Claude orquestra 35+ ferramentas. O pesquisador só valida.**"

**[Avançar]**

---

### SLIDE 12 — O Que Academic Hunter É e Não É (1.5 min)

> "Importante entender o papel de cada peça:
>
> ❌ **Não é um ChatGPT** — não gera texto, não inventa respostas.
> ❌ **Não é um agente autônomo** — é uma caixa de ferramentas que um agente IA usa.
> ✅ **É um motor de busca semântica** — entende o significado.
> ✅ **Viabiliza o que chamamos de Agentic RAG** — o agente IA orquestra ferramentas especializadas."
>
> [Se perguntarem: RAG = Retrieval-Augmented Generation. Agentic = com autonomia para planejar e iterar. Academic Hunter é a parte de RETRIEVAL do sistema.]

**[Avançar]**

---

### SLIDE 13 — Arquitetura Hexagonal (1.5 min)

> "Como o sistema foi construído: **arquitetura hexagonal, baseada em plugins**.
>
> **MCP Server** — interface com agentes de IA.
> **Core Domain** — o núcleo: modelo de paper, scoring, pipeline, PRISMA. Tudo funciona SEM LLM.
> **Plugin Layer** — cada conector é um plugin independente. Adicionar uma nova fonte não exige mexer no núcleo.
> **Infrastructure** — SQLite para cache, ChromaDB para vetores, config JSON.
>
> Essa arquitetura permite escalar horizontalmente — mais conectores, mais análises, mais formatos — sem reescrever o núcleo."

**[Avançar — Parte 4]**

---

## PARTE 4 — O MÉTODO (slides 14-17, ~10 min)

---

### SLIDE 14 — O Problema do Mean Pooling (2 min)

> "Agora vamos ao coração técnico: **Weight-Bleeding**.
>
> Quando um bi-encoder cria o embedding de um texto, ele usa **mean pooling** — a média de todas as palavras. O problema: a média trata TODO mundo igual.
>
> Exemplo: na frase 'O bi-encoder usa repetição de termos', as palavras 'O', 'de' têm o mesmo peso que 'bi-encoder'. O embedding não reflete a importância real dos termos.
>
> **Consequências:**
>
> 1. **Scores comprimidos** — artigos parecidos mas não exatos ficam com scores quase idênticos.
> 2. **Sem controle** — o pesquisador não consegue dizer 'isso é mais importante'."

**[Avançar]**

---

### SLIDE 15 — A Solução em 5 Passos (2.5 min)

> "A solução é simples.
>
> **Ideia central:** se repetir um termo W vezes no texto fizesse ele contribuir W vezes mais, podemos simular esse efeito DIRETAMENTE no espaço de embeddings — sem aumentar o texto, sem custo, sem GPU.
>
> **1.** Pesquisador define JSON com termos e pesos: CBDC=5, moeda digital=5, liquidez=2.
> **2.** Cada termo vira um embedding. O **centroide ponderado** é a média dos embeddings, cada um multiplicado pelo peso.
> **3.** Cada artigo é comparado com esse centroide.
> **4.** Artigos sobre CBDC sobem no ranking. Blockchain SEM CBDC não é afetado.
> **5.** Score final passa por raiz quadrada para resolver o problema dos scores comprimidos.
>
> Tudo em CPU, milissegundos por artigo, zero dados de treinamento."

**[Avançar]**

---

### SLIDE 16 — A Transformação Raiz Quadrada (2 min)

> "Por que a raiz quadrada? Porque as similaridades cosseno em 384 dimensões se concentram numa faixa estreita.
>
> **Antes (linear):** paper relevante (sim=0.30) → score 3.0. Irrelevante (sim=0.25) → 2.5. Diferença de 0.5 — quase invisível. Com threshold 3.5, ambos perdidos.
>
> **Depois (raiz quadrada):** relevante → √0.30×10 = 5.48. Irrelevante → 5.00. Diferença bem definida. O relevante passa.
>
> **Impacto real:** 59 papers a mais são aprovados com Weight-Bleeding + raiz quadrada contra o método tradicional."

**[Avançar]**

---

### SLIDE 17 — Resultados Experimentais (2 min)

> "Três números que comprovam:
>
> **96.8%** — correlação com vanilla. O ranking MUDA: 40% dos top-10 são diferentes.
>
> **-0.75** — correlação NEGATIVA entre domínios SLR e Blockchain. Prova que cada configuração produz um resultado único.
>
> **7.5× mais rápido** que cross-encoder. Consistente em 3 modelos (MiniLM, BGE, GTE).
>
> **59 artigos a mais** aprovados — papers que seriam perdidos são resgatados."

**[Avançar — Parte 5]**

---

## PARTE 5 — CONTRIBUIÇÃO (slides 18-22, ~5 min)

---

### SLIDE 18 — vs Concorrentes (1.5 min)

> "Como nos comparamos:
>
> - **16 fontes** contra 1 das concorrentes
> - **Scoring semântico, clusters, novidade, mapa** — ninguém mais tem
> - **API para agentes de IA via MCP** — único
> - **Custo zero e open source**
>
> Academic Hunter é a única ferramenta SLR gratuita com análise semântica E integração com IA."

**[Avançar]**

---

### SLIDE 19 — Posicionamento na Literatura (1 min)

> "Posição única: nenhum paper de 2025-2026 combina SLR + Weight-Bleeding + MCP. O survey do Singh cataloga 7 arquiteturas de Agentic RAG — nenhuma menciona SLR."

**[Avançar]**

---

### SLIDE 20 — Publicações (1 min)

> "Dois tracks: **JOSS** (a ferramenta, o ecossistema) e **Conferência** (o método Weight-Bleeding). Próximos passos: PyPI, Zenodo DOI, ORCID real, validação humana."

**[Avançar]**

---

### SLIDE 21 — Limitações (1 min)

> "Importante: AH é ótimo para SLRs exploratórias e triagem inicial, mas NÃO substitui revisão manual completa, meta-análise, avaliação de risco de viés. O pesquisador sempre valida."

**[Avançar]**

---

### SLIDE 22 — CTA (1 min)

> "Código no GitHub. Documentação no site. Instalem, testem, reportem bugs, contribuam. Perguntas?"

---

## Notas para o apresentador

### Timing

- Parte 1 (slides 1-4): ~7 min — não apressar
- Parte 2 (slides 5-9): ~10 min — embeddings é o conceito mais importante
- Parte 3 (slides 10-13): ~7 min — MCP explicado DEPOIS das funcionalidades
- Parte 4 (slides 14-17): ~10 min — ir devagar, slide 16 (sqrt) é o mais técnico
- Parte 5 (slides 18-22): ~5 min — fechamento

### Dicas

- **Slide 5** (embeddings): a analogia do mapa é essencial — gastar tempo aqui
- **Slide 10** (MCP): primeira vez que o termo MCP aparece — explicar como "protocolo padrão para conectar IAs a ferramentas"
- **Slide 12**: se perguntarem "o que é Agentic RAG?", responder: "agente IA orquestra ferramentas especializadas"
- **Slide 14** (mean pooling): usar a analogia da pesquisa de opinião
- **Slide 16** (sqrt): mostrar os números com calma — antes/depois
- **Slide 21** (limitações): falar com naturalidade — mostra transparência

### Glossário (se perguntarem)

- **Embedding**: vetor de números que representa o significado de um texto
- **MCP**: protocolo que permite IAs usarem ferramentas externas
- **RAG**: recuperar informação relevante antes de gerar resposta
- **Agentic RAG**: agente IA que planeja e executa múltiplas recuperações
- **Bi-encoder**: modelo que transforma texto em embedding
- **Cross-encoder**: modelo mais preciso que compara dois textos diretamente
