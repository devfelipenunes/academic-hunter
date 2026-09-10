# Avaliação de retrieval — coleção julgada piloto

Esta pasta guarda a coleção julgada (_qrels_) usada para medir qualidade de
recuperação, e o registro do que ela **pode e não pode** sustentar.

Antes dela, o projeto não tinha critério de sucesso para mudanças de retrieval:
comparava-se score com score, sem nada que dissesse se a ordenação ficou melhor.
Dois scripts consomem estes arquivos: `papers/experiments/retrieval_eval.py`
(estratégias de score) e `papers/experiments/fusion_comparison.py` (regras de
combinação dos dois sinais).

## Arquivos

| Arquivo                           | O que é                                                               |
| --------------------------------- | --------------------------------------------------------------------- |
| `qrels_pilot_genre_analysis.json` | 58 documentos julgados, 6 necessidades de informação, 348 julgamentos |

Formato e semântica estão em `src/academic_hunter/core/evaluation/qrels.py`.

## Como a coleção foi construída

**Corpus:** `results/run_20260910_010555/` — 274 papers sobre análise de gênero e
estrutura retórica em escrita acadêmica (EAP/ESP), produzidos pelo próprio
Academic Hunter.

**Pool (58 documentos):** união de duas seleções.

1. os **30 melhores por `Relevance_Score`**;
2. uma **amostra aleatória de 30** de todo o run (semente `20260910`).

A união existe por um motivo metodológico. Selecionar o pool apenas pelos
melhores scores **restringe a amplitude** da variável sob teste: se todos os
candidatos já têm score alto, o score deixa de discriminar dentro do pool e
parece pior do que é. A primeira versão desta coleção usava só o top-30 e
produziu exatamente esse artefato — reportava o baseline de citações como
vencedor. Com a amostra aleatória incluída, a amplitude vai de 3,3 a 17,8 e a
comparação passa a ter sentido.

**Julgamentos:** graus 0–2 por necessidade de informação
(0 = não relevante, 1 = parcialmente relevante, 2 = diretamente relevante),
atribuídos por leitura de título e abstract.

## O que os números mostram

`papers/experiments/fusion_comparison.py` fixa os dois sinais e varia apenas a
regra de combinação, então qualquer diferença é atribuível à fusão e não aos
componentes. Com 6 consultas e 58 documentos (todos julgados):

| Estratégia                                | nDCG@5 | nDCG@10 | nDCG@20 |    MRR |     AP |
| ----------------------------------------- | -----: | ------: | ------: | -----: | -----: |
| `keyword_only`                            | 0,3302 |  0,3952 |  0,5364 | 0,8056 | 0,5231 |
| **`shipped (weighted_norm)`**             | 0,3276 |  0,3934 |  0,5181 | 0,8056 | 0,5077 |
| `weighted_norm_50_50`                     | 0,3207 |  0,3822 |  0,5026 | 0,7222 | 0,4872 |
| `max_rank`                                | 0,2899 |  0,3398 |  0,4520 | 0,6389 | 0,4575 |
| `min_rank`                                | 0,2861 |  0,3335 |  0,4441 | 0,6111 | 0,4431 |
| `shipped (rank_geometric)` — regra antiga | 0,2604 |  0,3175 |  0,4500 | 0,5833 | 0,4445 |
| `rrf_60`                                  | 0,2798 |  0,3117 |  0,4471 | 0,5667 | 0,4421 |
| `embedding_only`                          | 0,2322 |  0,2860 |  0,3849 | 0,4667 | 0,4050 |
| `citations_baseline`                      | 0,1491 |  0,1084 |  0,2198 | 0,5611 | 0,2955 |

Quatro leituras:

1. **Fundir por ranks percentis destrói informação.** A regra antiga
   (`sqrt(rank_kw × rank_sem) × 10`) media _pior que cada um dos seus próprios
   componentes_. Converter os dois sinais em ranks antes de combinar joga fora a
   magnitude: um paper muito à frente em um sinal e mediano no outro fica
   indistinguível de um mediano nos dois. A regra em vigor passou a ser soma
   ponderada de scores min-max normalizados (`core/nlp/fusion.py`), com pesos
   70/30 — a proporção que os rótulos de modo do pipeline sempre alegaram e que
   a fórmula anterior não implementava.

2. **RRF é uma das piores** (0,3117). A receita usual para fundir rankings
   heterogêneos não se aplica aqui: RRF pressupõe listas com _documentos
   diferentes_, enquanto estes dois sinais são duas ordenações do **mesmo**
   conjunto. O amortecimento descarta sinal em vez de combiná-lo.

3. **O embedding é fraco dentro de um conjunto já filtrado.** Isolado, dá 0,2860
   — bem abaixo da palavra-chave. Explicação plausível: o candidato já passou
   pelo filtro de âncoras, então um sinal que mede proximidade ao vocabulário do
   domínio tem pouco a discriminar. Weight-Bleeding é um sinal de _relevância de
   domínio_ (útil para filtrar), não de _ordenação dentro do domínio_.

4. **Citações têm MRR 1,0 e nDCG@10 baixo** — sempre põe _algum_ relevante em
   primeiro, mas não os mais relevantes. Sinal forte de "isto é importante",
   fraco de "isto responde à necessidade".

A regra antiga continua disponível em `settings.fusion = "rank_geometric"` para
reproduzir execuções anteriores.

## Limites — leia antes de citar

- **Amostra pequena.** 6 consultas e 58 documentos. Indicativo, não conclusivo.
- **Julgamentos assistidos por máquina.** Foram atribuídos por leitura de
  título e abstract, não por especialistas nem por múltiplos anotadores. Não há
  medida de concordância entre anotadores. Trate como preliminar e revise.
- **Nenhum ranqueador usa o texto da consulta.** `keyword`, `embedding`,
  `weighted_norm` e `citations` são todos scores por documento, independentes da
  consulta — o Academic Hunter não tem ranking condicional à consulta. O que
  está sendo medido é a capacidade de _discriminar entre necessidades distintas
  dentro de um mesmo tópico_, não recuperação condicionada. Essa é uma lacuna de
  projeto real, não um artefato da medição.
- **Mede ordenação, não recall.** Como todo o pool é julgado, a métrica compara
  ranqueadores sobre um conjunto fixo. Um bom documento fora do pool não conta
  nem a favor nem contra. Para estender de "ordena bem" a "recupera bem", é
  preciso ampliar o pool e julgar mais documentos.
- **Julgamento em pool.** O pool veio dos resultados de um sistema, então
  documentos que nenhum sistema traria nunca foram julgados. Comparações
  relativas entre estratégias são válidas; recall absoluto não é.

## Como estender

1. Amplie o pool: rode o pipeline em outros tópicos, some os CSVs e julgue.
   O ideal é julgar também documentos que o sistema _não_ trouxe.
2. Adicione consultas ao `queries` do JSON, com julgamentos para os documentos
   do pool.
3. Rode `python papers/experiments/retrieval_eval.py --with-embedding`.
4. Verifique `min_coverage` no relatório: se cair muito abaixo de 1,0, a
   comparação está medindo o qrels e não o ranqueador.

O validador em `tests/test_evaluation_collection.py` checa, a cada execução da
suíte, que o arquivo carrega, que todo id julgado tem um documento correspondente
e que cada id ainda pode ser re-derivado do próprio documento — pool e
julgamentos não podem divergir em silêncio.

O arquivo é **autocontido**: os 58 documentos (título, DOI, abstract, ano, fonte,
citações e o score que o pipeline atribuiu) estão embutidos no JSON. O corpus
vive em `results/`, que está no `.gitignore`, então um qrels que apenas apontasse
para o CSV seria inútil em um clone novo. O CSV de origem continua registrado em
`provenance` para auditoria e para quem quiser ampliar a coleção localmente.
