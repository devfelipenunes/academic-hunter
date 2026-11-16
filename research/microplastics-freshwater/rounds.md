# Rodadas de busca e sensibilidade

As rodadas abaixo reutilizaram o cache de respostas no repositório e mantiveram as mesmas fontes sem credenciais. As rodadas exploratórias foram executadas antes de congelar o perfil versionado; algumas exclusões foram adicionadas ao longo da exploração. Portanto, a curva é diagnóstico de sensibilidade, não um benchmark perfeitamente controlado.

| Limite por fonte | Identificados | Crossref | ArXiv | DOAJ | Incluídos no corte original 12 |
|---:|---:|---:|---:|---:|---:|
| 100 | 844 | 500 | 294 | 50 | 6 |
| 200 | 1.373 | 1.000 | 323 | 50 | 12 |
| 250 | 1.623 | 1.250 | 323 | 50 | 14 |
| 300 | 1.873 | 1.500 | 323 | 50 | 15 |
| 400 | 2.373 | 2.000 | 323 | 50 | 18 |
| 500 | 2.873 | 2.500 | 323 | 50 | 24 |
| 700 | 3.873 | 3.500 | 323 | 50 | 37 |
| 1.000 | 5.373 | 5.000 | 323 | 50 | 60 |
| 1.500 | 7.873 | 7.500 | 323 | 50 | 108 |
| 2.000 | 10.373 | 10.000 | 323 | 50 | 166 |
| 2.500 | 12.873 | 12.500 | 323 | 50 | 215 |
| 3.000 | 15.373 | 15.000 | 323 | 50 | 273 |

A busca não atingiu platô até 3.000. Cada aumento acrescentou estudos que passavam o corte 12; o último passo trouxe 61. O Crossref chegou ao limite de 15.000 registros nas cinco combinações técnicas. O valor 3.000 é a maior rodada feita, não uma prova de exaustividade.

## Revisão do corte

Na rodada de 1.000, 79 candidatos passaram ano e âncora: 57 estavam acima de `_kw_score >= 12`, 22 abaixo. A triagem provisória por título e resumo quando disponível marcou entre os 22 abaixo: 20 potencialmente relevantes, 1 incerto e 1 fora do escopo. O piso do perfil foi reduzido para 6, que conserva os candidatos observados para revisão humana. Os escores baixos continuam registrados; a inclusão final é uma decisão humana.

## Comparação controlada do portão de contexto

Na mesma rodada de 1.000 por fonte, mesmo cache, fontes, exclusões e piso 6, foram comparados `context_rules_title_only=true` e `false`. A configuração estrita produziu 79 candidatos; aceitar o contexto também no resumo produziu 103 linhas de auditoria (102 acima do piso e 1 abaixo) e recuperou 24 registros adicionais. A revisão rápida dos títulos encontrou tanto falsos positivos óbvios (por exemplo, trabalhos marinhos e de partículas sem relação ambiental) quanto itens potencialmente elegíveis de ecotoxicidade, análise e transporte de microplásticos. Como a etapa é uma triagem de sensibilidade, escolhemos `false` para reduzir falsos negativos; o CSV mantém motivo e decisão humana em branco para adjudicação. Isso não mede a precisão final e não substitui revisar os 103 registros.


A revisão não cobre os 4.685 registros únicos rejeitados antes da pontuação por ano/âncora/contexto. O pipeline passou a exportá-los com motivos de triagem e campos de revisão. A próxima verificação de recall deve amostrar esse arquivo por fonte e motivo, além de auditar todos os candidatos pontuados.

## Fontes e limites

Na execução de referência, foram consultados Crossref (5.000), arXiv (323) e DOAJ (50). CORE, OpenAlex e Semantic Scholar ficaram como **não consultados**, sem zero enganoso, por não haver credenciais. Nenhuma fonte consultada ficou bloqueada. 23 dos 79 registros da rodada estrita tinham abstract no resultado e o lote de 56 DOIs sem resumo não recuperou abstracts do OpenAlex.

Sem credenciais, o número de candidatos e a curva não caracterizam toda a literatura. O limite de Crossref é aplicado por combinação de busca, os resultados dependem da sintaxe dos termos e a fonte não representa todas as bases bibliográficas. A decisão de parada precisa ser reavaliada após completar fontes e uma amostragem manual de excluídos.
