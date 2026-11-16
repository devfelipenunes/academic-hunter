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


A revisão não cobre todos os registros únicos rejeitados antes da pontuação por ano/âncora/contexto. O pipeline passou a exportá-los com motivos de triagem e campos de revisão. As amostras abaixo são de duas execuções distintas; seus tamanhos de população não devem ser confundidos.

## Fontes e limites

Na execução de referência, foram consultados Crossref (5.000), arXiv (323) e DOAJ (50). CORE e Semantic Scholar ficaram como **não consultados**, sem zero enganoso, por falta de credenciais; OpenAlex foi usado para tentar enriquecer resumos, mas não retornou resumo para os 56 candidatos originais. Nenhuma fonte da execução de referência ficou bloqueada.

Sem credenciais, o número de candidatos e a curva não caracterizam toda a literatura. O limite de Crossref é aplicado por combinação de busca, os resultados dependem da sintaxe dos termos e a fonte não representa todas as bases bibliográficas. A decisão de parada precisa ser reavaliada após completar fontes e uma amostragem manual de excluídos.


## Auditoria de falsos negativos e segunda triagem

A amostra estratificada inicial selecionou 77 exclusões (até 10 por fonte × motivo). A primeira leitura identificou dois estudos de ecotoxicidade com *Daphnia magna* que não deveriam ser descartados. Após normalizar as categorias, a segunda triagem independente concordou em 71/77; duas decisões foram adjudicadas por fontes primárias e quatro divergências ficaram incertas. Fontes primárias confirmam os ensaios de microplástico em *Daphnia* e seu uso como organismo de água doce: [artigo de Bosker et al.](https://www.sciencedirect.com/science/article/abs/pii/S0269749119304191), [ensaio de Rehse et al. no PubMed](https://pubmed.ncbi.nlm.nih.gov/27010171/) e [orientação da EPA sobre espécies de teste de água doce](https://www.epa.gov/system/files/documents/2024-12/module-2-usepa-npdes-testing-methods.pdf). A reconciliação final contém 63 exclusões provisórias, 12 incertos e dois estudos recuperados por adjudicação externa.

Foi acrescentado `daphnia` ao contexto e o rerun recuperou cinco registros de ecotoxicidade com esse organismo. Uma auditoria subsequente motivou a inclusão de outros organismos-modelo de água doce, águas superficiais e efluentes. O perfil foi ampliado e reexecutado: a matriz passou a 149 candidatos (148 acima do piso 6, um abaixo). Os registros e pareceres por avaliador estão em `consolidated-adjudication-round3.csv`.

A segunda leitura independente da matriz inicial de 103 marcou 24 incluir, 12 excluir e 67 incertos. A concordância exata foi 44/103; divergências foram mantidas incertas na reconciliação. Resultado: 22 inclusões consensuais, 11 exclusões consensuais e 70 incertos. Para os 46 registros acrescentados depois, houve 23 consensos de decisão (13 inclusão, 5 exclusão e 5 incerto); os demais foram adjudicados como 19 registros de fonte/tratamento para contexto, um de água potável tratada e um fora de escopo, um mantido incerto e um incluído após confirmação do resumo primário do estudo do Rio Raritan. Na atualização de 16/11/2026, os 76 incertos foram adjudicados por título/resumo: 47 inclusão provisória, 20 contexto e 9 exclusão; 72 tinham resumo recuperado e quatro ficaram somente com título. A matriz de 149 agora contém 22 incluídos, 61 incluídos provisoriamente, 39 para contexto e 27 excluídos. Isso é adjudicação por um único avaliador de IA, não revisão por dois especialistas humanos; todos os candidatos incluídos ainda precisam de texto integral e extração.

A amostra pós-ajuste selecionou 77 dos 4.615 excluídos; houve concordância em 65/77. A reconciliação deixou 50 exclusões provisórias e 27 incertos. Não se confirmou outro falso negativo nessa amostra; os 27 casos incertos precisam de adjudicação. Nenhuma das amostras deve ser usada para extrapolar sensibilidade global: as frações de amostragem variam muito entre estratos.

## Busca suplementar OpenAIRE

A integração MCP continuou indisponível, mas a API pública do OpenAIRE Graph foi consultada diretamente em 2026-11-16 usando quatro buscas: `microplastics freshwater river`, `microplastics freshwater lake reservoir`, `microplastics freshwater ecotoxicity` e `microplastics freshwater analytical methods`. Foram retornados 286 registros únicos após deduplicação entre consultas; a primeira encontrou 834 resultados e foi limitada aos 100 primeiros; as outras retornaram 19, 81 e 92. Uma comparação por DOI/título exato contra candidatos e descartados locais identificou oito correspondências e 278 registros sem correspondência exata. Uma busca lexical de títulos não encontrou outras duplicatas prováveis, mas não substitui a checagem manual de versões. A triagem dos 278 marcou 174 inclusão provisória, 73 incertos e 31 exclusões provisórias. Após enriquecimento OpenAlex, 272 têm resumo e seis continuam somente com título. A triagem OpenAIRE permanece separada da matriz local e do PRISMA: falta uma segunda revisão independente, verificação de versão e integração deduplicada antes de compor a síntese. Consultas e respostas estão em `openaire-search-round2.json`; triagem deduplicada em `openaire-screening-unique-round2.csv`. A busca usa a API Graph pública documentada pelo [OpenAIRE](https://graph.openaire.eu/docs/11.4.0/apis/graph-api/research-products/).

A recuperação de abstracts foi tentada em Crossref e OpenAlex para os 56 candidatos sem resumo na matriz inicial, sem encontrar novos resumos. Na busca OpenAIRE, 4 dos 10 registros sem resumo receberam abstracts pelo OpenAlex; 6 continuam avaliados somente pelo título. CORE e Semantic Scholar continuam não consultados por falta de credenciais. DataCite não foi consultado porque esta etapa visou publicações, não datasets/software. Uma comparação lexical de títulos não apontou duplicatas aproximadas adicionais; ela não substitui verificação de versões e DOI.


## Busca suplementar OpenAlex e adjudicação de 16/11/2026

Cinco consultas públicas OpenAlex foram executadas sem chave, cada uma limitada aos 100 primeiros resultados por relevância. Foram recuperados 500 itens e 426 únicos após deduplicação entre consultas; 323 não tinham correspondência exata de DOI/título na matriz local e no OpenAIRE. Removidas cinco duplicatas internas (variantes/versões), restaram 318 registros. A triagem única de título/resumo marcou 168 candidatos a estudo primário, 91 itens de contexto, 41 registros de literatura cinzenta, 15 exclusões e três casos que exigem conferência de escopo no texto integral. O conjunto pode conter versões que a correspondência exata não detectou, e o limite por consulta não permite alegar exaustividade. A lista de consultas e contagens está em `openalex-search-log-round4.json`; as decisões em `openalex-screening-round4.csv`.

Também foram recuperados resumos para os 76 casos pendentes da matriz: 72 resumos, quatro registros somente com título. O registro de decisão e a fonte associada estão em `candidate-adjudication-round4.csv`; os resumos integrais recuperados não foram guardados como novos artefatos do projeto. Síntese narrativa e limitações em `scientific-review.md`.
