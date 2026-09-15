<div align="center">
  <h1>🎯 Academic Hunter</h1>
  <p><b>Automated Systematic Literature Reviews with Semantic Intelligence</b></p>

[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/github/license/devfelipenunes/academic-hunter)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/github/actions/workflow/status/devfelipenunes/academic-hunter/test.yml?branch=main&label=tests)](https://github.com/devfelipenunes/academic-hunter/actions)
[![MCP Ready](https://img.shields.io/badge/Protocol-MCP_Ready-orange.svg)](https://modelcontextprotocol.io/)
</div>

Academic Hunter is an open-source Systematic Literature Review (SLR) tool that combines **multi-source search** (7 databases searched in parallel, 15 accessible in total), **semantic relevance scoring** (Weight-Bleeding), **topic clustering** (BERTopic), **novelty detection**, **extractive summarization**, and a **Model Context Protocol (MCP) server** — all running locally on CPU, with zero API costs.

---

## 🚀 Quickstart: Primeira SLR em 1 minuto

O Academic Hunter é um **servidor MCP**: conecte-o a um agente de IA e peça a revisão em linguagem natural.

```bash
# Instale
pip install git+https://github.com/devfelipenunes/academic-hunter.git

# Crie o config a partir do exemplo — o servidor não funciona sem ele
curl -fsSL https://raw.githubusercontent.com/devfelipenunes/academic-hunter/main/config.example.json -o config.json

# Inicie o servidor MCP (stdio)
academic-mcp

# Ou em modo HTTP (SSE) para acesso remoto
academic-mcp -t sse --host 0.0.0.0 --port 8080
```

Conectado ao agente, basta pedir — _"rode uma revisão sistemática sobre X"_ — e ele orquestra as tools (`run_search`, `semantic_search`, `cluster_papers`).

## 📖 Tutorial Completo

Veja o [tutorial passo a passo](docs/tutorial.md) — 10 minutos para fazer sua primeira SLR completa.

---

## ✨ Principais Funcionalidades

### 🔍 Busca Multi-Fonte

O pipeline consulta **7 fontes acadêmicas em paralelo**: arXiv, Crossref, Semantic Scholar, OpenAlex, CORE, DBLP e DOAJ — com deduplicação entre todas. Outras 8 ficam disponíveis sob demanda pelas tools MCP: Europe PMC, OpenCitations, Unpaywall, Lens.org, OpenAIRE, bioRxiv, medRxiv e DataCite.

### 🧠 Weight-Bleeding Scoring

Método original de ponderação semântica configurável via centroide ponderado em espaço de embeddings — permite que o pesquisador defina quais termos são mais importantes sem modificar o modelo, sem GPU, sem dados rotulados.

### 📊 13 Análises com o Mesmo Modelo (MiniLM 22MB)

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
| Dentro do paper | `chunk_search`        | Busca por trecho no full text, com seção e offsets  |

### 🤖 MCP Server — Integração com Agentes de IA

O Academic Hunter expõe **44 ferramentas, 4 recursos e 2 prompts** via Model Context Protocol. Qualquer agente de IA (Claude, ChatGPT, LangChain) pode orquestrar revisões sistemáticas completas autonomamente.

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

| Comando               | Descrição                          |
| --------------------- | ---------------------------------- |
| `academic-mcp`        | Inicia o servidor MCP (stdio)      |
| `academic-mcp -t sse` | Inicia o servidor MCP em modo HTTP |

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
│                    MCP Server (44 tools)                     │
│  4 Resources · 2 Prompts · Health Check · SSE Transport     │
├─────────────────────────────────────────────────────────────┤
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐│
│ │  Search  │ │  NLP     │ │  MCP     │ │  Exporters       ││
│ │  7 APIs  │ │  Scorer  │ │  Tools   │ │  CSV/Bib/RIS/MD  ││
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
