# Tutorial: Primeira SLR em 10 Minutos

Este tutorial guia você por uma Revisão Sistemática da Literatura completa usando o Academic Hunter — sem precisar editar JSON, sem programação, sem GPU.

## O que você vai aprender

1. Instalar o Academic Hunter
2. Fazer uma SLR completa no modo interativo
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

## 2. Modo Interativo (recomendado)

O modo mais fácil de usar o Academic Hunter. Você só precisa dizer o tópico:

```bash
academic-hunter interactive
```

O programa vai guiar você por todo o processo:

```
🧪 Academic Hunter — Modo Interativo
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 Qual o tópico da sua revisão?
> Central Bank Digital Currencies and Financial Stability

🔍 Descobrindo jargões sobre 'Central Bank Digital Currencies...'...
✅ 12 termos encontrados automaticamente

📋 Configuração sugerida:
    Core_Concepts:
      · digital currencies (peso: 5.0)
      · financial stability (peso: 5.0)
      · central bank (peso: 5.0)
      ...
    Context:
      · monetary policy (peso: 2.0)
      ...

Aceitar configuração e iniciar busca? [S/n] S

🔍 Buscando em 16 fontes acadêmicas...
✅ 733 papers encontrados
📦 Papers indexados no ChromaDB

📊 ANÁLISES
  1. Ver ranking completo dos papers
  2. Agrupar por tema (clusters)
  3. Detectar papers inovadores (outliers)
  4. Ver evolução temporal
  5. Mapa da pesquisa (2D)
  6. Exportar resultados
  7. Encerrar
```

## 3. Busca Manual (sem modo interativo)

Se preferir configurar manualmente, edite o arquivo `config.json`:

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

Depois execute:

```bash
academic-hunter run
```

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

```bash
# Pelo CLI interativo: menu → opção 6
# Pelo MCP:
export_report(format="csv")
export_report(format="bibtex")
export_report(format="ris")
export_report(format="json")
```

## Próximos passos

- 📖 Leia a [documentação completa](https://devfelipenunes.github.io/academic-hunter)
- 🐛 Reporte bugs em [github.com/devfelipenunes/academic-hunter/issues](https://github.com/devfelipenunes/academic-hunter/issues)
- ⭐ Contribua com o projeto no GitHub
