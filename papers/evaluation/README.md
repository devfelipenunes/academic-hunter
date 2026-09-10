# Avaliação de retrieval — coleção julgada

Esta pasta guarda a coleção julgada (_qrels_) usada para medir qualidade de
recuperação, e o registro do que ela **pode e não pode** sustentar.

Antes dela, o projeto não tinha critério de sucesso para mudanças de retrieval:
comparava-se score com score, sem nada que dissesse se a ordenação ficou melhor.
Dois scripts consomem estes arquivos: `papers/experiments/retrieval_eval.py`
(estratégias de score) e `papers/experiments/fusion_comparison.py` (regras de
combinação dos dois sinais).

## Arquivos

| Arquivo                           | O que é                                                             |
| --------------------------------- | ------------------------------------------------------------------- |
| `qrels_pilot_genre_analysis.json` | 108 documentos julgados, 11 consultas, 598 julgamentos, dois tópicos |

Formato e semântica estão em `src/academic_hunter/core/evaluation/qrels.py`.

## Como a coleção foi construída

Dois tópicos deliberadamente distantes, para que a avaliação não seja um ajuste
a um único domínio:

| Tópico | Corpus de origem | Papers | Pool |
| --- | --- | ---: | ---: |
| `genre_analysis` — análise de gênero / move analysis (EAP/ESP) | `results/run_20260910_010555` | 274 | 58 |
| `blockchain_governance` — blockchain e governança digital | `results/run_20260727_152204` | 1.538 | 50 |

**Pool de cada tópico** = os melhores por `Relevance_Score` **união** uma amostra
aleatória de igual tamanho (semente `20260910`).

A união existe por um motivo metodológico. Selecionar o pool apenas pelos
melhores scores **restringe a amplitude** da variável sob teste: se todos os
candidatos já têm score alto, o score deixa de discriminar dentro do pool e
parece pior do que é. A primeira versão desta coleção usava só o top-30 e
produziu exatamente esse artefato — reportava o baseline de citações como
vencedor, com nDCG@10 de 0,5162. Com a amostra aleatória incluída, a amplitude
vai de 3,0 a 29,7 e a comparação passa a ter sentido. Há teste de regressão para
isso, **por pool** (`test_each_pool_spans_the_score_range`).

**Cada consulta declara seu pool.** As consultas de um tópico são ranqueadas
sobre os documentos daquele tópico, não sobre a união — um documento de
blockchain não carrega julgamento para uma consulta de análise de gênero, e
contá-lo como irrelevante penalizaria o ranqueador por um pool que ele nunca
recebeu. Ver `documents_for` em `core/evaluation/qrels.py`.

**Julgamentos:** graus 0–2 por necessidade de informação (0 = não relevante,
1 = parcialmente relevante, 2 = diretamente relevante), atribuídos por leitura de
título e abstract.

## O que os números mostram

`fusion_comparison.py` fixa os dois sinais e varia apenas a regra de combinação,
então qualquer diferença é atribuível à fusão e não aos componentes:

| Estratégia                                 | nDCG@5 | nDCG@10 |    MRR |     AP |
| ------------------------------------------ | -----: | ------: | -----: | -----: |
| `keyword_only`                             | 0,3234 |  0,3364 | 0,8008 | 0,3941 |
| **`shipped (weighted_norm)`**              | 0,2782 |  0,3223 | 0,8056 | 0,3816 |
| `max_rank`                                 | 0,3046 |  0,2813 | 0,8160 | 0,3716 |
| `weighted_norm_50_50`                      | 0,2901 |  0,2785 | 0,7803 | 0,3790 |
| `rrf_60`                                   | 0,2076 |  0,2334 | 0,4538 | 0,3200 |
| `arith_rank`                               | 0,1592 |  0,2068 | 0,3629 | 0,3012 |
| `shipped (rank_geometric)` — regra antiga  | 0,1527 |  0,2012 | 0,3389 | 0,2926 |
| `embedding_only`                           | 0,1490 |  0,1991 | 0,6089 | 0,2908 |
| `min_rank`                                 | 0,1332 |  0,1954 | 0,3977 | 0,2965 |
| `citations_baseline`                       | 0,0932 |  0,1037 | 0,3716 | 0,2598 |

Cinco leituras:

1. **Fundir por ranks percentis destrói informação.** A regra antiga
   (`sqrt(rank_kw × rank_sem) × 10`) media _pior que cada um dos seus próprios
   componentes_. Converter os dois sinais em ranks antes de combinar joga fora a
   magnitude: um paper muito à frente em um sinal e mediano no outro fica
   indistinguível de um mediano nos dois. A regra em vigor é soma ponderada de
   scores min-max normalizados (`core/nlp/fusion.py`), 70/30 — a proporção que os
   rótulos de modo do pipeline sempre alegaram e que a fórmula anterior não
   implementava. Ganho de **+0,135 nDCG@10** sobre a regra antiga.

2. **A melhor estratégia depende do tópico**, e é por isso que o relatório traz a
   quebra por tópico:

   | Estratégia                     | `genre_analysis` | `blockchain_governance` |
   | ------------------------------ | ---------------: | ----------------------: |
   | `exported_score` (do run)      |           0,1850 |              **0,2488** |
   | `keyword`                      |       **0,4291** |                  0,2251 |
   | `citations_baseline`           |           0,1084 |                  0,0981 |

   Em análise de gênero o keyword domina (0,4291); em blockchain o score que o
   próprio run reportou é o melhor (0,2488). Uma média única sobre dois corpora
   não relacionados esconde exatamente isso — uma mudança que ajuda um tópico e
   arruína o outro passaria como melhoria.

3. **RRF está entre as piores** (0,2334). A receita usual para fundir rankings
   heterogêneos não se aplica aqui: RRF pressupõe listas com _documentos
   diferentes_, enquanto estes dois sinais são duas ordenações do **mesmo**
   conjunto. O amortecimento descarta sinal em vez de combiná-lo.

4. **O embedding é fraco dentro de um conjunto já filtrado** (0,1991 isolado).
   Explicação plausível: o candidato já passou pelo filtro de âncoras, então um
   sinal que mede proximidade ao vocabulário do domínio tem pouco a discriminar.
   Weight-Bleeding é um sinal de _relevância de domínio_ (útil para filtrar), não
   de _ordenação dentro do domínio_.

5. **`min_rank` sobreajusta.** Foi o melhor com 3 consultas (0,3692) e caiu para
   nono com 11 (0,1954). Trocar o default com base na primeira medição teria sido
   um erro — e é o argumento para manter a coleção crescendo antes de decidir
   qualquer coisa por margem pequena.

A regra antiga continua disponível em `settings.fusion = "rank_geometric"` para
reproduzir execuções anteriores.

## Limites — leia antes de citar

- **Amostra pequena.** 11 consultas e 108 documentos. Indicativo, não conclusivo.
  Diferenças na terceira casa decimal não são sinal.
- **Julgamentos de anotador único, assistidos por máquina.** Foram atribuídos por
  leitura de título e abstract, não por especialistas nem por múltiplos
  anotadores. Não há medida de concordância entre anotadores — a
  reprodutibilidade dos _números_ é alta, a das _etiquetas_ é desconhecida.
  **Pendente: revisão pelo autor do projeto**, que passa a ser o anotador de
  fato; até então, trate como preliminar.
- **Nenhum ranqueador usa o texto da consulta.** Todas as estratégias são scores
  por documento, independentes da consulta — o Academic Hunter não tem ranking
  condicional à consulta. O que se mede é a capacidade de _discriminar entre
  necessidades distintas dentro de um mesmo tópico_, não recuperação
  condicionada. É lacuna de projeto, não artefato da medição.
- **Mede ordenação, não recall.** Todo o pool é julgado, então a métrica compara
  ranqueadores sobre um conjunto fixo. Um bom documento fora do pool não conta
  nem a favor nem contra. Para estender de "ordena bem" a "recupera bem", é
  preciso ampliar o pool e julgar mais documentos.
- **Julgamento em pool.** O pool veio dos resultados de um sistema, então
  documentos que nenhum sistema traria nunca foram julgados. Comparações
  relativas entre estratégias são válidas; recall absoluto não é.
- **`exported_score` não é comparação justa.** Seus ranks foram calculados sobre
  o run inteiro (centenas de papers), enquanto a avaliação ranqueia só o pool.

## Como estender

1. Amplie o pool: rode o pipeline em outros tópicos, some os CSVs e julgue.
   Julgar documentos que o sistema **não** trouxe é o que estende o alcance da
   conclusão.
2. Adicione consultas ao `queries` do JSON, com `topic`, `pool` e julgamentos
   para os documentos do pool.
3. Rode `python papers/experiments/retrieval_eval.py --with-embedding` e
   `python papers/experiments/fusion_comparison.py`.
4. Verifique `min_coverage` no relatório: se cair abaixo de 1,00, a comparação
   está medindo o qrels e não o ranqueador.

O validador em `tests/test_evaluation_collection.py` checa, a cada execução da
suíte, que o arquivo carrega, que todo id julgado tem um documento, que cada id
pode ser re-derivado do próprio documento, que toda consulta declara seu pool,
que os membros do pool têm julgamento para aquela consulta e que pools de tópicos
distintos não se sobrepõem.

O arquivo é **autocontido**: os 108 documentos (título, DOI, abstract, ano,
fonte, citações e o score que o pipeline atribuiu) estão embutidos no JSON. O
corpus vive em `results/`, que não é versionado, então um qrels que apenas
apontasse para os CSVs seria inútil em um clone novo. Os CSVs de origem
continuam registrados em `provenance` para auditoria e para quem quiser ampliar a
coleção localmente.
