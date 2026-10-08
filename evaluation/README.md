# Avaliação de retrieval — coleção julgada

Esta pasta guarda a coleção julgada (_qrels_) usada para medir qualidade de
recuperação, e o registro do que ela **pode e não pode** sustentar.

Antes dela, o projeto não tinha critério de sucesso para mudanças de retrieval:
comparava-se score com score, sem nada que dissesse se a ordenação ficou melhor.

## Arquivos

| Arquivo                                    | O que é                                                              |
| ------------------------------------------ | -------------------------------------------------------------------- |
| `qrels_pilot_genre_analysis.json`          | 108 documentos julgados, 11 consultas, 598 julgamentos, dois tópicos |
| `fulltext_coverage.json`                   | O desfecho de cada documento julgado na busca por full text          |
| `pool_candidates_blockchain_ai.json`       | 50 documentos do run `20261006_153320`, **ainda sem julgamentos**    |
| `pool_grading_page.html`                   | Página gerada que apresenta esses 50 e exporta os julgamentos        |
| `build_pool_grading_page.py`               | O gerador da página                                                  |
| `rebuild_pool.py`                          | Re-chaveia um pool existente sob as regras de identidade atuais      |
| `fusion_comparison.py`                     | Mede as regras de fusão contra um qrels, sobre um run real           |

Formato e semântica estão em `src/academic_hunter/core/evaluation/qrels.py`.

## Como a coleção foi construída

Dois tópicos deliberadamente distantes, para que a avaliação não seja um ajuste
a um único domínio:

| Tópico                                                         | Corpus de origem              | Papers | Pool |
| -------------------------------------------------------------- | ----------------------------- | -----: | ---: |
| `genre_analysis` — análise de gênero / move analysis (EAP/ESP) | `results/run_20260910_010555` |    274 |   58 |
| `blockchain_governance` — blockchain e governança digital      | `results/run_20260727_152204` |  1.538 |   50 |

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

## Um terceiro tópico: blockchain × IA, pronto a julgar

`pool_candidates_blockchain_ai.json` é um pool novo, de um tópico novo e de um
run que ainda não tem julgamento nenhum: 50 documentos do run `20261006_153320`,
blockchain × inteligência artificial, escolhidos como os 25 melhores por
`Relevance_Score` **união** 25 aleatórios (semente `20261006`) — a mesma receita
dos dois pools acima, e pelo mesmo motivo.

Ele existe por um motivo específico e medido. O único qrels do repositório
(`qrels_pilot_genre_analysis.json`) **não tem um único id em comum** com este
corpus, e `calibrate_inclusion_threshold` mede um corte contra ids julgados. Sem
julgamentos deste pool, a ferramenta não tem contra o que medir, e
`min_inclusion_score` continua sendo um número escolhido a dedo — hoje em 5, um
corte que **não decide nada**: 310 dos 311 papers avaliados passam por ele.

### Como julgar

    ./venv/bin/python evaluation/build_pool_grading_page.py \
        evaluation/pool_candidates_blockchain_ai.json \
        evaluation/pool_grading_page.html

Depois abra a página **por HTTP**, não por `file://`:

    ./venv/bin/python -m http.server 8000
    # http://localhost:8000/evaluation/pool_grading_page.html

Servir importa: navegadores recusam armazenamento local em origem `file://`, e é
lá que os julgamentos ficam entre uma visita e outra. A página detecta a recusa e
avisa em vez de perdê-los em silêncio; o botão de exportar funciona de qualquer
forma.

A página apresenta os 50 documentos **em ordem fixa derivada do id**, e não na
ordem do arquivo — que é exatamente "os 25 melhores primeiro". Mostrar essa ordem
convida o julgador a concordar com a ordenação que ele existe para testar, e a
concordância seria então medida e reportada como acurácia. A pontuação do
pipeline fica atrás de um botão, desligada por omissão, pelo mesmo motivo.

Ao terminar, **Exportar qrels** produz o JSON. Salve como
`evaluation/qrels_blockchain_ai.json` — é esse arquivo que
`calibrate_inclusion_threshold` lê.

### A consulta fica registrada no pool

O pool nomeia o run de origem mas não a pergunta. `ranking_query` foi acrescentado
ao arquivo, lido do backup de configuração que o banco de histórico guarda às
`2026-10-06T15:32:29` — a última escrita antes do run das `15:33:20`, e idêntica
em todos os backups desde as `13:10`. A proveniência exata está em
`ranking_query_provenance`, dentro do próprio arquivo. Julgar sem a consulta
declarada é julgar contra o que o julgador lembra do tema, e a precisão resultante
mede uma pergunta diferente da que ordenou o run.

### O que este pool permite, e o que não permite

- **Permite calibrar o corte de inclusão.** É para isso que ele existe.
- **Permite escolher os pesos** (citações, embedding). `fusion_comparison.py`
  refunde os sinais que o run gravou sob cada regra e mede as ordenações contra
  os julgamentos — ver «O que os números mostram», abaixo. Como o pool ainda não
  tem julgamentos, a ferramenta responde «sem julgamentos» em vez de inventar uma
  tabela; é o julgamento que a põe a funcionar, e é a razão para julgar.
- **Um julgador, leitura de título e abstract.** Os mesmos limites da coleção
  piloto, e valem igualmente aqui.

`tests/test_pool_collection.py` checa, a cada execução da suíte, que o pool é
chaveado pelos ids que `doc_id_for` deriva, que declara a consulta, e que a página
embute exatamente o pool que ela julga — a falha silenciosa seria uma página
gerada de um pool mais antigo, coletando julgamentos para documentos que já
saíram. Ele checa também que os ids correspondem ao que o run de origem produz
**hoje**: um pool escrito antes de o pipeline começar a gravar o DOI do arXiv
continua internamente coerente e, ao mesmo tempo, aponta para chaves que a
distribuição de pontuações já não tem.

### O pool foi re-chaveado uma vez, e o motivo importa

O pipeline passou a gravar o DOI que o `URL` de um arXiv implica (`ResolveDoiStep`).
O id de um documento é `doc_id_for(title, doi)`, então **16 dos 50 ids mudaram** —
todos de `title:…` para `doi:10.48550/arxiv.…`. Julgar antes disso teria deixado
32% dos julgamentos órfãos, e `calibrate_inclusion_threshold` conta um julgamento
órfão como uma falha, em silêncio.

`rebuild_pool.py` re-chaveia **no lugar** e não re-sorteia: os documentos são os
que já estavam no arquivo, encontrados no CSV do próprio run pelo título. Um
documento que não esteja nesse CSV aborta o arquivo inteiro em vez de adivinhar a
chave — uma chave adivinhada é um julgamento perdido. O arquivo ganha um bloco
`regeneration` com a data, a regra e a lista de renomeações.

    ./venv/bin/python evaluation/rebuild_pool.py \
        evaluation/pool_candidates_blockchain_ai.json
    ./venv/bin/python evaluation/build_pool_grading_page.py \
        evaluation/pool_candidates_blockchain_ai.json \
        evaluation/pool_grading_page.html

A página tem de ser reconstruída em seguida: ela embute os ids, e uma página
antiga coleta julgamentos em chaves que já não existem.

## O que os números mostram

`fusion_comparison.py` fixa os dois sinais e varia apenas a regra de combinação,
então qualquer diferença é atribuível à fusão e não aos componentes:

    ./venv/bin/python evaluation/fusion_comparison.py \
        results/run_20261006_193350/score_distribution_20261006_193350.json \
        evaluation/qrels_blockchain_ai.json    # o arquivo que a página de julgamento produz

Reconstruído contra `core/nlp/fusion.py` — que é o código que efetivamente roda —,
ele chama `fuse_scores` em vez de repetir a fórmula. A tabela abaixo foi medida pelo
script anterior, que saiu do repositório com `papers/` em `6a48f1c`, e é mantida como
registro do que **ele** mediu na coleção piloto (11 consultas, dois tópicos) — números
que não são comparáveis a uma medição de hoje, porque a coleção não é a mesma.

| Estratégia                                | nDCG@5 | nDCG@10 |    MRR |     AP | Reproduzível hoje |
| ----------------------------------------- | -----: | ------: | -----: | -----: | ----------------- |
| `keyword_only`                            | 0,3234 |  0,3364 | 0,8008 | 0,3941 | sim — `weighted_norm_1_0` |
| **`shipped (weighted_norm)`**             | 0,2782 |  0,3223 | 0,8056 | 0,3816 | sim — `weighted_norm_70_30` |
| `max_rank`                                | 0,3046 |  0,2813 | 0,8160 | 0,3716 | **não** |
| `weighted_norm_50_50`                     | 0,2901 |  0,2785 | 0,7803 | 0,3790 | sim |
| `rrf_60`                                  | 0,2076 |  0,2334 | 0,4538 | 0,3200 | **não** |
| `arith_rank`                              | 0,1592 |  0,2068 | 0,3629 | 0,3012 | **não** |
| `shipped (rank_geometric)` — regra antiga | 0,1527 |  0,2012 | 0,3389 | 0,2926 | sim — `rank_geometric` |
| `embedding_only`                          | 0,1490 |  0,1991 | 0,6089 | 0,2908 | sim — `weighted_norm_0_1` |
| `min_rank`                                | 0,1332 |  0,1954 | 0,3977 | 0,2965 | **não** |
| `citations_baseline`                      | 0,0932 |  0,1037 | 0,3716 | 0,2598 | sim |

As quatro linhas marcadas **não** são as que este repositório não consegue medir de
novo, e não são reimplementadas aqui: `fuse_scores` implementa `IMPLEMENTED_STRATEGIES` — duas regras, não seis — e mapeia
qualquer outra string para `weighted_norm` **sem avisar**, então pedir `rrf_60` pelo
nome devolveria os números de `weighted_norm` sob o rótulo errado. O comparador
recusa em vez de medir, e nomeia as quatro no relatório.

**O que os runs gravaram, medido.** Nos sete `score_distribution_*.json` do
repositório, a coluna `Relevance_Score` é reproduzível — uma casa decimal, a precisão
com que é gravada — por **`weighted_norm` com peso 100% no keyword sobre
`_bm25_score`**, e por mais nenhuma das regras padrão. Ou seja: nesses runs o embedding
contribuiu zero. Não é um bug do comparador, é o ramo de `ranking_query` em
`RecomputeRanksStep`: quando há consulta declarada e `fusion_weights` não está
configurado, os pesos passam a ser 1,0/0,0. O default 70/30 vale para runs **sem**
consulta declarada, e é por isso que o relatório nomeia qual sinal esparso leu.

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

   | Estratégia                | `genre_analysis` | `blockchain_governance` |
   | ------------------------- | ---------------: | ----------------------: |
   | `exported_score` (do run) |           0,1850 |              **0,2488** |
   | `keyword`                 |       **0,4291** |                  0,2251 |
   | `citations_baseline`      |           0,1084 |                  0,0981 |

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

## Full-text: o que o retrieval por trecho acrescenta

Uma medição comparou recuperar **trechos** de 180 palavras contra ranquear sobre
título + abstract. A hipótese foi declarada **antes** da medição.

**O conjunto de candidatos é restrito, e isso não é o erro do pool top-30.**
25 dos 108 documentos julgados **não têm DOI nenhum** — nenhum sistema de
full-text conseguiria alcançá-los. O teto estrutural é 65,5% do pool de
`genre_analysis` e 90,0% do de `blockchain_governance`. Pontuar o chunk-level
sobre o pool inteiro mediria esse teto, não o retriever. Então **todas** as
estratégias — BM25 inclusive — ranqueiam o mesmo conjunto restrito
(`pool ∩ documentos com chunks`), e a cobertura sai impressa ao lado de cada
número. Restrição por disponibilidade dos dados é coisa diferente de restrição
pela métrica sob teste; a segunda é o erro que esta coleção já cometeu.

| Estratégia                     | nDCG@5 | nDCG@10 | nDCG@20 |    MRR |
| ------------------------------ | -----: | ------: | ------: | -----: |
| `paper_level (bm25)`           | 0,5091 |  0,4801 |  0,4616 | 0,8000 |
| **`chunk_level (max, all)`**   | 0,6346 |  0,5565 |  0,5329 | 0,9000 |
| `chunk_level (mean_top3)`      | 0,6790 |  0,5729 |  0,5489 | 1,0000 |
| `chunk_level@50 (max)`         | 0,6346 |  0,5565 |  0,5329 | 0,9000 |
| `hybrid (bm25 + chunk, 50/50)` | 0,5582 |  0,5240 |  0,5005 | 0,8000 |

A hipótese se sustenta — `chunk_level` ganha **+0,0764** de nDCG@10 sobre o
BM25 —, mas **a base é estreita e precisa ser lida junto**: 5 das 11 consultas,
16 documentos candidatos e **um tópico só**. As seis consultas de
`genre_analysis` ficaram de fora porque apenas 3 dos 58 documentos do pool têm
chunks. A quebra por tópico imprime `n/a` para `genre_analysis` exatamente por
isso; o ganho é de `blockchain_governance` (0,4801 → 0,5565). Também vale notar
que `mean_top3` supera `max`: com 16 candidatos as duas reduções ordenam quase a
mesma lista curta, e a diferença é mais ruído do que sinal.

**Cobertura: 19 dos 108 documentos** (737 chunks) — 19 obtidos, 35 sem cópia em
acesso aberto, 29 falhas de download e 25 sem DOI. As falhas estão registradas
com o motivo em `fulltext_coverage.json`, e isso importa: `download_failed`
cobre três situações distintas — erro transitório, cópia aberta que é apenas uma
landing page, e editora recusando cliente que não seja navegador — e só a
primeira vale retentar. A distinção não é teórica: **uma segunda passada
recuperou um documento** que havia falhado na primeira. Neste corpus a perna do
**Europe PMC não entregou nada**: a coleção é de linguística aplicada, que o PMC
não indexa. Ela ganha o lugar dela em corpora biomédicos, não neste, e o
relatório de cobertura diz qual perna entregou cada documento.

## Limites — leia antes de citar

- **Amostra pequena.** 11 consultas e 108 documentos. Indicativo, não conclusivo.
  Diferenças na terceira casa decimal não são sinal.
- **Julgamentos de anotador único, assistidos por máquina.** Foram atribuídos por
  leitura de título e abstract, não por especialistas nem por múltiplos
  anotadores. Não há medida de concordância entre anotadores — a
  reprodutibilidade dos _números_ é alta, a das _etiquetas_ é desconhecida.
  **Pendente: revisão pelo autor do projeto**, que passa a ser o anotador de
  fato; até então, trate como preliminar. O que a revisão encontra hoje:
  - São **598 julgamentos** sobre 108 documentos e 11 consultas — 458 com grau 0,
    65 com 1 e 75 com 2; o limiar de relevância é 1 (`RELEVANT_THRESHOLD`), então
    140 pares contam como relevantes.
  - **95 dos 108 documentos** trazem título e abstract embutidos no próprio
    qrels, e podem ser revisados sem rede. **13 têm abstract vazio** — 76
    julgamentos, 66 deles em `genre_analysis` e 10 em `blockchain_governance` —
    e exigiriam resolver o DOI. **25 não têm DOI nenhum** e só podem ser
    julgados pelo título.
  - Não há ferramenta de revisão no projeto: o formato é editável à mão, e
    `save_qrels` preserva a ordem e os blocos que não interpreta, de modo que
    revisar e salvar produz um diff só com o que mudou.
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
- **A medição de chunk é de um tópico só.** Cinco consultas, 16 documentos
  candidatos, `blockchain_governance`. Não é base para dizer que retrieval por
  trecho ganha de BM25 em geral — é base para dizer que ganhou ali, e para
  justificar ampliar a cobertura antes de afirmar mais.
- **A cobertura de full text é baixa e desigual** (19/108, e 3/58 no tópico de
  análise de gênero contra 16/50 no de blockchain), e o que ela mede está
  limitado pelo que foi possível baixar. Toda a comparação vive dentro do
  subconjunto que tem chunk; a cobertura sai ao lado das métricas justamente
  para que ninguém leia o número sem ela.
- **O qrels não contém necessidades específicas.** O ganho genuíno do retrieval
  por trecho é responder "qual dataset usaram", "quantos anotadores codificaram"
  — perguntas que esta coleção não faz, porque foi julgada por relevância
  tópica. Um resultado nulo aqui seria limitação da coleção para esta pergunta,
  não veredito sobre a técnica.

## Como estender

1. Amplie o pool: rode o pipeline em outros tópicos, some os CSVs e julgue.
   Julgar documentos que o sistema **não** trouxe é o que estende o alcance da
   conclusão.
2. Adicione consultas ao `queries` do JSON, com `topic`, `pool` e julgamentos
   para os documentos do pool.
3. Meça com `build_rankings` e `evaluate_run`, de
   `academic_hunter.core.evaluation`, sobre a coleção ampliada.
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
