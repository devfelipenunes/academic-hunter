# Revisão: microplásticos em água doce

Este diretório guarda o perfil versionado da busca, o protocolo de triagem e os resultados da avaliação para que as execuções possam ser reconstruídas.

## Executar

No repositório, instale `academic-hunter[dev]` e aponte o projeto para o perfil:

```bash
export ACADEMIC_HUNTER_CONFIG="$PWD/research/microplastics-freshwater/search_profile.json"
uv run academic-mcp
```

O perfil usa 1.000 registros por fonte para pesquisa iterativa, aceita regras de contexto encontradas no título ou resumo (`context_rules_title_only=false`) e mantém candidatos com `_kw_score >= 6`. Após uma auditoria de descartados que encontrou estudos relevantes com *Daphnia magna*, o contexto foi ampliado para incluir espécies-modelo de água doce, água superficial e termos de efluente/tratamento; o rerun resultou em 149 linhas de auditoria (148 acima do piso, 1 abaixo). O corte 12 deixou 22 de 79 candidatos fora; uma triagem preliminar com títulos e resumos disponíveis considerou 20 potencialmente relevantes, um incerto e um fora do escopo. Por isso, 6 é um piso de recuperação para revisão humana, não uma decisão científica de inclusão. Para uma rodada ampliada, execute `run_search` com limite 3.000. Esse valor não significa saturação: a varredura anterior ainda adicionou candidatos aprovados pelo corte. Uma comparação controlada com contexto apenas no título encontrou 24 registros adicionais quando o contexto do resumo foi aceito; o conjunto maior foi preferido para reduzir falsos negativos e será revisto manualmente.

As credenciais nunca pertencem ao perfil versionado. Configure `OPENALEX_API_KEY`, `SEMANTIC_SCHOLAR_API_KEY` e `CORE_API_KEY` no ambiente (ou os campos correspondentes de `settings.api_keys` no `config.json` local ignorado pelo Git). O relatório deve marcar qualquer fonte indisponível como não consultada.

## Artefatos esperados por execução

- `academic_dataset_*.csv`: estudos que passaram o corte.
- `screening_candidates_*.csv`: todos os candidatos que passaram ano e âncora, antes do corte, com decisão automática e colunas para adjudicação humana.
- `screening_exclusions_*.csv`: registros únicos rejeitados antes da pontuação, com o motivo da falha e colunas para amostragem. Os arquivos de amostra e reconciliação registram o desenho, as decisões provisórias e as divergências.
- `run_stats_*.json`: cobertura, estatísticas, impressão digital e configuração usada.
- Relatório Markdown e fluxo PRISMA.

A primeira passada, com contexto limitado ao título e corte 12, encontrou 57 candidatos acima do corte e 22 abaixo; depois o piso foi reduzido para 6. A matriz mais recente tem 149 linhas e sua reconciliação provisória registra 36 inclusões, 37 exclusões do escopo principal e 76 incertos. As decisões ainda precisam de validação humana especializada e texto integral para os casos incertos. A pesquisa OpenAIRE está separada em `openaire-screening-unique-round2.csv`: são 278 registros sem correspondência exata local, ainda sem segunda revisão e fora do PRISMA. A planilha de triagem é evidência de trabalho, não substitui o texto integral.
