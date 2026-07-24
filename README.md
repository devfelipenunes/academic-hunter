<div align="center">
  <h1>🎯 Academic Hunter</h1>
  <p><b>Automated Systematic Literature Reviews with Semantic Intelligence</b></p>

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MCP Ready](https://img.shields.io/badge/Protocol-MCP_Ready-orange.svg)](https://modelcontextprotocol.io/)
[![Tests](https://img.shields.io/badge/tests-155_passing-green.svg)](https://github.com/devfelipenunes/academic-hunter)
</div>

Academic Hunter is an open-source Systematic Literature Review (SLR) tool that combines **multi-source search** (16 academic databases), **semantic relevance scoring** (Weight-Bleeding), **topic clustering** (BERTopic), **novelty detection**, **extractive summarization**, and a **Model Context Protocol (MCP) server** — all running locally on CPU, with zero API costs.

---

## 🚀 Quickstart: Primeira SLR em 1 minuto

```bash
# Instale
pip install git+https://github.com/devfelipenunes/academic-hunter.git

# Modo interativo — só diga o tópico
academic-hunter interactive

# Ou inicie o servidor MCP para agentes de IA
academic-mcp
```

## 📖 Tutorial Completo

Veja o [tutorial passo a passo](docs/tutorial.md) — 10 minutos para fazer sua primeira SLR completa.

---

## ✨ Principais Funcionalidades

### 🔍 Busca Multi-Fonte

Conecta-se a **16 fontes acadêmicas simultaneamente**: arXiv, Crossref, Semantic Scholar, OpenAlex, CORE, DBLP, DOAJ, Europe PMC, OpenCitations, Unpaywall, Lens.org, OpenAIRE, ClinicalTrials.gov, bioRxiv, medRxiv, DataCite.

### 🧠 Weight-Bleeding Scoring

Método original de ponderação semântica configurável via centroide ponderado em espaço de embeddings — permite que o pesquisador defina quais termos são mais importantes sem modificar o modelo, sem GPU, sem dados rotulados.

### 📊 12 Análises com o Mesmo Modelo (MiniLM 22MB)

| Análise         | Tool MCP              | O que faz                                           |
| --------------- | --------------------- | --------------------------------------------------- |
| Busca semântica | `semantic_search`     | Encontra papers por CONCEITO, não por palavra exata |
| Re-ranking      | `rerank_search`       | Bi-encoder + cross-encoder para maior precisão      |
| Clustering      | `cluster_papers`      | Agrupa automaticamente por tema (BERTopic)          |
| Outliers        | `find_novel_papers`   | Detecta papers inovadores/disruptivos               |
| Snowballing     | `find_related_papers` | "Mais like this" para cada paper                    |
| Tópicos         | `trending_topics`     | Identifica os assuntos mais frequentes              |
| Evolução        | `topic_evolution`     | Mostra como os temas mudam ao longo dos anos        |
| Mapa 2D         | `visualize_landscape` | Projeção UMAP de todos os papers                    |
| Duplicatas      | `semantic_dedup`      | Detecta duplicatas por similaridade de embedding    |
| Resumo          | `summarize_paper`     | Resumo extrativo via MMR                            |
| Citações        | `get_citation_count`  | Contagem de citações via OpenCitations              |
| Acesso Aberto   | `find_open_access`    | Versão OA de papers pagos via Unpaywall             |

### 🤖 MCP Server — Integração com Agentes de IA

O Academic Hunter expõe **35+ ferramentas, 4 recursos e 2 prompts** via Model Context Protocol. Qualquer agente de IA (Claude, ChatGPT, LangChain) pode orquestrar revisões sistemáticas completas autonomamente.

```bash
# Inicia o servidor (stdio)
academic-mcp

# Ou em modo HTTP (SSE) para acesso remoto
academic-mcp -t sse --host 0.0.0.0 --port 8080
```

### 📦 Exportação Multi-Formato

CSV, BibTeX, RIS, JSON, Markdown, PRISMA — e exportação direta para **Obsidian**.

---

## 🔧 Comandos

| Comando                       | Descrição                                        |
| ----------------------------- | ------------------------------------------------ |
| `academic-hunter interactive` | Modo interativo guiado (não precisa editar JSON) |
| `academic-hunter run`         | Executa o pipeline com a configuração atual      |
| `academic-hunter benchmark`   | Benchmark de 3 modos de scoring                  |
| `academic-mcp`                | Inicia o servidor MCP (stdio)                    |
| `academic-mcp -t sse`         | Inicia o servidor MCP em modo HTTP               |

---

## 📊 Comparação com Ferramentas Existentes

| Recurso              | Academic Hunter    | ASReview       | Rayyan | Covidence |
| -------------------- | ------------------ | -------------- | ------ | --------- |
| Código aberto        | ✅                 | ✅             | ❌     | ❌        |
| Fontes de dados      | **16**             | 1 (importação) | 1      | 1         |
| Scoring semântico    | ✅ Weight-Bleeding | ❌             | ❌     | ❌        |
| Cluster automático   | ✅                 | ❌             | ❌     | ❌        |
| Detecção de novidade | ✅                 | ❌             | ❌     | ❌        |
| MCP / API para IA    | ✅                 | ❌             | ❌     | ❌        |
| Offline-first        | ✅                 | ✅             | ❌     | ❌        |
| Custo                | **Zero**           | Zero           | $$$    | $$$$      |

---

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                    MCP Server (35+ tools)                    │
│  4 Resources · 2 Prompts · Health Check · SSE Transport     │
├─────────────────────────────────────────────────────────────┤
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐│
│ │  Search  │ │  NLP     │ │  MCP     │ │  Exporters       ││
│ │  16 APIs │ │  Scorer  │ │  Tools   │ │  CSV/Bib/RIS/MD  ││
│ └──────────┘ └──────────┘ └──────────┘ └──────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

---

## 📚 Leia os Papers

- **JOSS**: "Academic Hunter: An Open-Source Systematic Literature Review Tool with Agentic RAG and Embedding-Space Relevance Scoring"
- **Conferência**: "Weight-Bleeding: Configurable Semantic Relevance Scoring via Input-Level Term Repetition in Bi-Encoders"

Ambos em [`papers/`](papers/).

---

## 📄 Licença

MIT License — use, modifique, distribua livremente.

## 🤝 Contribua

Issues, pull requests e feedback são bem-vindos!
