# Protocolo de busca e triagem

## Pergunta de revisão

Como microplásticos e nanoplásticos ocorrem, são transportados e se acumulam em ecossistemas de água doce; quais métodos os detectam e quantificam; e quais efeitos ecológicos são relatados?

## Escopo

- **População/ambiente:** água doce continental, incluindo rios, lagos, córregos, reservatórios, bacias, wetlands e sedimentos associados.
- **Exposição:** microplásticos, nanoplásticos, fragmentos e fibras plásticas dentro do escopo de tamanho e definição que cada estudo declarar.
- **Desfechos:** ocorrência, abundância/distribuição, transporte/destino, métodos de detecção/quantificação e efeitos ecológicos.
- **Período:** 2015 em diante, conforme o perfil.
- **Fontes:** arXiv, Crossref, DOAJ, OpenAlex, Semantic Scholar e CORE; fonte não consultada deve ser explicitada no PRISMA e nunca contada como zero resultados encontrados.

## Inclusão automática atual

O sistema exige correspondência com âncoras de microplásticos e contexto de água doce encontrado no título ou resumo, aplica termos de exclusão no título e conserva `_kw_score >= 6`. A comparação controlada mostrou 24 candidatos adicionais ao aceitar o resumo como contexto; essa opção foi escolhida para favorecer recuperação e exige triagem manual dos falsos positivos. A triagem preliminar marcou 20 dos 22 registros abaixo do corte anterior (12) como potencialmente relevantes, um como incerto e um fora do escopo; o corte 6 é um piso para manter candidatos à revisão, não um critério científico de inclusão. A inclusão final exige leitura humana de título e resumo e, nos casos incertos, texto integral.

## Critérios de triagem humana

Marcar cada candidato com uma decisão: `incluir`, `excluir` ou `incerto`.

- **Incluir:** estudo primário ou revisão pertinente que trate de micro/nanoplásticos em ambiente de água doce continental e reporte ocorrência, destino/transporte, métodos ou impacto ecológico.
- **Excluir:** ambiente exclusivamente marinho/salino; plástico maior sem resultado de micro/nanoplástico; estudo de saúde humana/alimento sem ambiente de água doce; método/legislação sem dado ou análise relevante ao tema; registro editorial, duplicado ou retratado.
- **Incerto:** água salobra/estuário, transição rio-mar, títulos ambíguos, ausência de resumo ou escopo de tamanho indefinido. Resolver pela leitura do resumo/texto integral e registrar o motivo.

Não excluir automaticamente uma palavra ambígua sem validar o estudo. Em particular, registros com `brackish`, `estuary/estuaries`, `mangrove`, `coastal` e `freshwater` misturados exigem adjudicação humana.

Cada execução salva os candidatos pontuados em `screening_candidates_*.csv` e os itens únicos descartados antes da pontuação em `screening_exclusions_*.csv`. Revise todos os candidatos pontuados; para aferir o portão de âncora/contexto, sorteie e revise uma amostra estratificada dos excluídos por motivo (`year`, `title_exclusion`, `context_missing`, `anchor_missing`) e por fonte.

## Registro de método

Para cada execução, guardar data, commit, impressão digital da configuração, período, limites por consulta, fontes consultadas/indisponíveis, identificados por fonte, duplicatas, excluídos por ano/âncora/escore e decisões humanas. Reportar curva de novos estudos relevantes por limite; não declarar saturação apenas por atingir limite de API.
