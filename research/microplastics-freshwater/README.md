# Revisão: microplásticos em água doce

Este diretório guarda o perfil versionado da busca, o protocolo de triagem e os resultados da avaliação para que as execuções possam ser reconstruídas.

## Executar

No repositório, instale `academic-hunter[dev]` e aponte o projeto para o perfil:

```bash
export ACADEMIC_HUNTER_CONFIG="$PWD/research/microplastics-freshwater/search_profile.json"
uv run academic-mcp
```

O perfil usa 1.000 registros por fonte para pesquisa iterativa, aceita regras de contexto encontradas no título ou resumo (`context_rules_title_only=false`) e mantém candidatos com `_kw_score >= 6`. O corte 12 deixou 22 de 79 candidatos fora; uma triagem preliminar com títulos e resumos disponíveis considerou 20 potencialmente relevantes, um incerto e um fora do escopo. Por isso, 6 é um piso de recuperação para revisão humana, não uma decisão científica de inclusão. Para uma rodada ampliada, execute `run_search` com limite 3.000. Esse valor não significa saturação: a varredura anterior ainda adicionou candidatos aprovados pelo corte. Uma comparação controlada com contexto apenas no título encontrou 24 registros adicionais quando o contexto do resumo foi aceito; o conjunto maior foi preferido para reduzir falsos negativos e será revisto manualmente.

As credenciais nunca pertencem ao perfil versionado. Configure `OPENALEX_API_KEY`, `SEMANTIC_SCHOLAR_API_KEY` e `CORE_API_KEY` no ambiente (ou os campos correspondentes de `settings.api_keys` no `config.json` local ignorado pelo Git). O relatório deve marcar qualquer fonte indisponível como não consultada.

## Artefatos esperados por execução

- `academic_dataset_*.csv`: estudos que passaram o corte.
- `screening_candidates_*.csv`: todos os candidatos que passaram ano e âncora, antes do corte, com decisão automática e colunas para adjudicação humana.
- `screening_exclusions_*.csv`: registros únicos rejeitados antes da pontuação, com o motivo da falha de ano/contexto/âncora e colunas para amostragem humana.
- `run_stats_*.json`: cobertura, estatísticas, impressão digital e configuração usada.
- Relatório Markdown e fluxo PRISMA.

A primeira passada, com contexto limitado ao título e o corte antigo 12, encontrou 57 incluídos, 22 candidatos abaixo do corte e 34 incluídos sem resumo. A rodada ampliada com contexto no título ou resumo tem 103 linhas de auditoria, ainda sem adjudicação humana completa. Esses registros precisam de revisão por título/resumo antes de qualquer conclusão científica. A planilha de triagem é evidência de trabalho, não substitui o texto integral.
