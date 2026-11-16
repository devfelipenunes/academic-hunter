# Revisão: microplásticos em água doce

Este diretório guarda o perfil versionado da busca, o protocolo, as decisões de triagem e a síntese científica. O relatório atual está em [`scientific-review.md`](scientific-review.md).

## Executar

No repositório, instale `academic-hunter[dev]` e aponte o projeto para o perfil:

```bash
export ACADEMIC_HUNTER_CONFIG="$PWD/research/microplastics-freshwater/search_profile.json"
uv run academic-mcp
```

O perfil conserva `_kw_score >= 6` como piso de recuperação, não como critério científico de inclusão. Contexto pode aparecer no título ou resumo, o que reduz falsos negativos e aumenta falsos positivos que exigem triagem manual. Credenciais nunca pertencem ao perfil versionado. CORE e Semantic Scholar não foram consultados por falta de credenciais; o conector MCP Academic Hunter estava indisponível nesta rodada.

## Estado da revisão

A matriz local consolidada tem 149 registros: 22 incluídos, 61 incluídos provisoriamente, 39 destinados a contexto e 27 excluídos. Os 76 casos antes incertos foram adjudicados por título/resumo; 72 tinham resumo e quatro ficaram somente com título. A avaliação foi feita por um único avaliador de IA. Os 83 registros incluídos/incluídos provisoriamente ainda precisam de leitura integral e extração de dados antes de compor uma revisão sistemática fechada.

As buscas suplementares permanecem separadas: OpenAIRE encontrou 278 registros sem correspondência exata local; OpenAlex trouxe 318 candidatos únicos novos após deduplicação interna. Seus fluxos não foram incorporados ao total da matriz principal nem ao PRISMA. Consulte [`rounds.md`](rounds.md) e [`scientific-review.md`](scientific-review.md) para os limites e as contagens.

## Artefatos

- `candidate-adjudication-round4.csv`: evidência, fonte e decisão dos 76 casos adjudicados.
- `consolidated-adjudication-round3.csv`: matriz consolidada atualizada.
- `openalex-screening-round4.csv`: triagem suplementar por título/resumo, sem abstracts.
- `openalex-dedup-audit-round4.csv`: cinco duplicatas internas removidas.
- `openalex-search-log-round4.json` / `.csv`: consultas, limites e contagens; sem dumps integrais de abstracts.
- `openaire-screening-unique-round2.csv`: triagem suplementar OpenAIRE.
