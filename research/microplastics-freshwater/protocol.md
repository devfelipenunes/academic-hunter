# Protocolo de busca e triagem

## Pergunta de revisão

Como microplásticos e nanoplásticos ocorrem, são transportados e se acumulam em ecossistemas de água doce; quais métodos os detectam e quantificam; e quais efeitos ecológicos são relatados?

## Escopo

- **População/ambiente:** água doce continental, incluindo rios, lagos, córregos, reservatórios, bacias, wetlands e sedimentos associados.
- **Exposição:** microplásticos, nanoplásticos, fragmentos e fibras plásticas dentro do escopo de tamanho e definição que cada estudo declarar.
- **Desfechos:** ocorrência, abundância/distribuição, transporte/destino, métodos de detecção/quantificação e efeitos ecológicos.
- **Período:** 2015 em diante, conforme o perfil.
- **Fontes:** arXiv, Crossref, DOAJ, OpenAlex, Semantic Scholar e CORE; fonte não consultada deve ser explicitada no PRISMA e nunca contada como zero resultados encontrados.

## Atualização da revisão em 16/11/2026

A matriz de referência contém 149 registros, dos quais 83 estão classificados como incluídos ou incluídos provisoriamente, 39 como contexto e 27 como excluídos. Os 76 registros que estavam incertos foram avaliados com título/resumo recuperado quando disponível: 72 tinham resumo e quatro permaneceram somente com título. Essa adjudicação foi feita por um único avaliador de IA. As buscas suplementares OpenAIRE e OpenAlex estão em fluxos separados; não somar seus registros ao PRISMA da matriz principal sem reconciliar versões e revisar em duplicata. O relatório de síntese atual está em `scientific-review.md`.

Esses resultados não encerram a triagem sistemática: antes de afirmar elegibilidade final, ler texto integral dos candidatos, extrair os desfechos e métodos com formulário padronizado, e obter segunda avaliação humana independente com resolução documentada de discordâncias. Para uma busca exaustiva, consultar bases especializadas adicionais (por exemplo, Web of Science/Scopus) ou documentar indisponibilidade.

## Inclusão automática atual

O sistema exige âncora de micro/nanoplástico e contexto no título ou resumo, aplica termos de exclusão no título e conserva `_kw_score >= 6`. O contexto também aceita táxons-modelo de água doce (por exemplo, *Daphnia*, *zebrafish*), água superficial e vias de efluente/tratamento: a auditoria confirmou falsos negativos de ecotoxicidade com *Daphnia magna*. Essa ampliação favorece recuperação, mas também traz estudos de tratamento, água potável e ambientes marinhos para triagem manual. Resultados somente de wastewater/tratamento não equivalem automaticamente a resultados de água doce; mantê-los separados como vias/fontes e incluir apenas se pertinentes à pergunta. A comparação controlada encontrou 24 candidatos adicionais ao aceitar contexto do resumo em vez de apenas do título. A triagem preliminar marcou 20 dos 22 registros abaixo do corte anterior (12) como potencialmente relevantes, um como incerto e um fora do escopo; o corte 6 é um piso para manter candidatos à revisão, não um critério científico de inclusão. A inclusão final exige leitura humana de título e resumo e, nos casos incertos, texto integral.

## Critérios de triagem humana

Marcar cada candidato com uma decisão: `incluir`, `excluir` ou `incerto`.

- **Incluir:** estudo primário ou revisão pertinente que trate de micro/nanoplásticos em ambiente de água doce continental e reporte ocorrência, destino/transporte, métodos ou impacto ecológico.
- **Excluir:** ambiente exclusivamente marinho/salino; plástico maior sem resultado de micro/nanoplástico; estudo de saúde humana/alimento sem ambiente de água doce; método/legislação sem dado ou análise relevante ao tema; registro editorial, duplicado ou retratado.
- **Incerto:** água salobra/estuário, transição rio-mar, títulos ambíguos, ausência de resumo ou escopo de tamanho indefinido. Resolver pela leitura do resumo/texto integral e registrar o motivo.

Não excluir automaticamente uma palavra ambígua sem validar o estudo. Em particular, registros com `brackish`, `estuary/estuaries`, `mangrove`, `coastal` e `freshwater` misturados exigem adjudicação humana.

Cada execução salva os candidatos pontuados em `screening_candidates_*.csv` e os itens únicos descartados antes da pontuação em `screening_exclusions_*.csv`. Revise todos os candidatos e os desacordos entre revisores. Para aferir o portão, use amostras estratificadas por motivo (`year`, `title_exclusion`, `context_missing`, `anchor_missing`) e fonte. As amostras atuais usam 10 por estrato quando disponível, portanto são diagnósticas e não estimam uma taxa global ponderada de falsos negativos.

## Registro de método

Para cada execução, guardar data, commit, impressão digital da configuração, período, limites por consulta, fontes consultadas/indisponíveis, identificados por fonte, duplicatas, excluídos por ano/âncora/escore e decisões humanas. Reportar curva de novos estudos relevantes por limite; não declarar saturação apenas por atingir limite de API.
