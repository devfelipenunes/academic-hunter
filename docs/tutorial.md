# Tutorial: Primeira SLR em 10 Minutos

Este tutorial guia você por uma Revisão Sistemática da Literatura completa usando o Academic Hunter — sem precisar editar JSON, sem programação, sem GPU.

## O que você vai aprender

1. Instalar o Academic Hunter
2. Fazer uma SLR completa conversando com um agente de IA
3. Explorar os resultados com análises automáticas
4. Exportar para seu formato preferido

---

## 1. Instalação

```bash
# Clone o repositório
git clone https://github.com/devfelipenunes/academic-hunter.git
cd academic-hunter

# Crie um ambiente virtual e instale
python3 -m venv venv
source venv/bin/activate
pip install -e .

# (Opcional) Para funcionalidades avançadas de ML
pip install -e ".[ml]"
```

## 2. Uso via MCP (recomendado)

O Academic Hunter é um **servidor MCP** — a forma de usá-lo é conectá-lo a um agente de IA:

```bash
academic-mcp          # stdio
academic-mcp -t sse   # HTTP/SSE, para acesso remoto
```

Conectado, basta pedir em linguagem natural:

> "Rode uma revisão sistemática sobre Central Bank Digital Currencies and Financial Stability"

O agente orquestra as tools: `quick_topic_discovery` descobre o jargão da área,
`update_config` monta a configuração, `run_search` executa a busca, e
`cluster_papers`, `find_novel_papers` e `visualize_landscape` analisam o resultado.

## 3. Configuração Manual

Para controle fino, edite o arquivo `config.json`:

```json
{
  "topic": "CBDC and atomic settlement",
  "anchors": {
    "Settlement": ["atomic settlement", "finality"],
    "CBDC": ["central bank digital currency"]
  },
  "technical_weights": {
    "atomic settlement": 5.0,
    "finality": 3.0,
    "cbdc": 5.0,
    "digital currency": 4.0
  },
  "settings": {
    "start_year": 2020,
    "limit_per_query": 100,
    "user_email": "seu@email.com"
  }
}
```

Depois, execute a busca pelo agente conectado — tool `run_search`.

## 4. Análises Avançadas (via MCP)

Após a busca, você pode usar as ferramentas MCP para análises mais profundas.
Inicie o servidor MCP:

```bash
academic-mcp
```

Conecte qualquer cliente MCP (Claude Desktop, LangChain, etc.) e use as ferramentas:

| Tool                  | Para que serve             | Exemplo                                                        |
| --------------------- | -------------------------- | -------------------------------------------------------------- |
| `semantic_search`     | Buscar papers por conceito | `semantic_search(query="CBDC banking implications", top_k=10)` |
| `trending_topics`     | Ver tópicos quentes        | `trending_topics(min_papers=3)`                                |
| `cluster_papers`      | Agrupar por tema           | `cluster_papers(top_k=500, min_cluster_size=5)`                |
| `find_novel_papers`   | Detectar outliers          | `find_novel_papers(top_k=200, contamination=0.1)`              |
| `find_related_papers` | Snowballing semântico      | `find_related_papers(query="CBDC financial stability")`        |
| `visualize_landscape` | Mapa 2D da pesquisa        | `visualize_landscape(top_k=500)`                               |
| `topic_evolution`     | Evolução temporal          | `topic_evolution(top_k=500)`                                   |
| `semantic_dedup`      | Duplicatas semânticas      | `semantic_dedup(threshold=0.88)`                               |
| `summarize_paper`     | Resumo de um paper         | `summarize_paper(doi="10.1016/j.jfe.2023.01.001")`             |
| `get_citation_count`  | Citações de um paper       | `get_citation_count(doi="10.1016/j.jfe.2023.01.001")`          |

## 5. Exemplo de Fluxo Completo via MCP

Conectando o Claude Desktop ao Academic Hunter, você pode simplesmente dizer:

> "Faça uma revisão sistemática sobre o impacto de CBDCs na estabilidade financeira"

O Claude vai:

1. Explorar o tópico com `quick_topic_discovery`
2. Configurar a busca com `update_config`
3. Executar o pipeline com `run_search`
4. Analisar resultados com `semantic_search`, `cluster_papers`, `find_novel_papers`
5. Gerar o mapa da pesquisa com `visualize_landscape`
6. Exportar para Obsidian com `export_to_obsidian`

## 6. Exportação

Pelo MCP:

```
export_report(format="csv")
export_report(format="bibtex")
export_report(format="ris")
export_report(format="json")
```

## Próximos passos

- 📖 Leia a [documentação completa](https://devfelipenunes.github.io/academic-hunter)
- 🐛 Reporte bugs em [github.com/devfelipenunes/academic-hunter/issues](https://github.com/devfelipenunes/academic-hunter/issues)
- ⭐ Contribua com o projeto no GitHub
