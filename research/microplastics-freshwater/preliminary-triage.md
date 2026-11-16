# Triagem preliminar da busca de microplásticos em água doce

Execução inicial para a triagem detalhada: `results/run_20261116_155250`, 1.000 por fonte, corte automático original `_kw_score >= 12`. Execução ampliada inicial: `results/run_20261116_160845`; após falsos negativos confirmados, a execução mais recente é `results/run_20261116_163334`, contexto por título/resumo e indicadores de água doce ampliados. Matriz local: `screening_adjudication_preliminary.csv` no diretório daquela execução. O classificador e a revisão de título/resumo foram feitos por IA e são **provisórios**, não substituem adjudicação por pesquisador.

## Resultado da primeira passada

Dos 79 candidatos que passaram ano e âncora, a triagem provisória marcou 76 para possível inclusão, 2 incertos e 1 exclusão. O material analisado inclui títulos, 23 resumos já presentes nos registros e resumos consultados para 8 estudos em fontes bibliográficas. Ainda assim, 48 registros ficaram avaliados somente pelo título.

O corte 12 teria removido 22 candidatos: 20 parecem potencialmente relevantes, um é incerto e um foi excluído. Isso aponta risco de falso negativo elevado para o corte 12. O perfil versionado foi alterado para `_kw_score >= 6`, que preserva os 79 candidatos deste conjunto para revisão humana. A redução do corte é uma medida de recuperação, não evidência de que os 76 provisórios estejam cientificamente incluídos. A comparação inicial do portão ampliou a matriz para 103 registros (102 acima do piso 6 e 1 abaixo). A auditoria dos excluídos confirmou falsos negativos em *Daphnia*; o perfil atualizado gerou 149 registros (148 acima do piso, 1 abaixo).

## Decisões que mudaram após consultar os resumos

- O artigo sobre ingestão por peixes amazônicos mede partículas de 1–15 mm, incluindo a fração microplástica; provisoriamente incluído. [PubMed](https://pubmed.ncbi.nlm.nih.gov/30388680/)
- O estudo do Lago Vitória mede explicitamente micro-, meso- e macroplásticos; provisoriamente incluído. [PubMed](https://pubmed.ncbi.nlm.nih.gov/31677873/)
- O estudo do Danúbio relata uma descarga de microplástico industrial em tributário de água doce; provisoriamente incluído apesar do foco regulatório. [PubMed](https://pubmed.ncbi.nlm.nih.gov/25734504/)
- O modelo dos Grandes Lagos estima massa de microplástico para Superior, Huron e Erie; provisoriamente incluído. [PubMed](https://pubmed.ncbi.nlm.nih.gov/27988025/)
- O estudo do rio Tamsui mede microplásticos de 0,3–5 mm em quatro rios do sistema; provisoriamente incluído. [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0269749119352200)
- O estudo do Thames mistura um sítio descrito como fluvial e outro estuarino; mantido incerto até separar os dados do sítio fluvial. [PubMed](https://pubmed.ncbi.nlm.nih.gov/27697381/)
- O estudo do Yangtze trata de trechos fluviais do médio/baixo rio, mas inclui influência de intrusão salina; mantido incerto até confirmar que resultados de água doce são separáveis. [PubMed](https://pubmed.ncbi.nlm.nih.gov/30597469/)
- O estudo de Townsville/Ross River contabiliza lixo/plástico genérico que entra por drenagens, sem determinar fração microplástica no resumo; excluído do conjunto de microplásticos, pode ser citado apenas como contexto. [PubMed](https://pubmed.ncbi.nlm.nih.gov/31179993/)

## Resumos ausentes

Uma busca em lote no OpenAlex para os 56 candidatos sem resumo no registro retornou os trabalhos, mas nenhum `abstract_inverted_index`. A triagem por título pode errar a faixa de tamanho, o sítio de coleta e a natureza do estudo. A matriz registra a base de evidência e notas por candidato; os casos sem resumo continuam provisórios.

## Estado da revisão ampliada

A matriz mais recente tem 149 registros e foi consolidada em `consolidated-adjudication-round3.csv`: 36 inclusões (22 consensuais na primeira matriz e 14 provisórias após a triagem dos acréscimos), 37 exclusões do escopo principal e 76 incertos. Entre os 46 acréscimos à matriz inicial de 103, as duas leituras concordaram em 23 decisões; casos de wastewater/tratamento foram separados como contexto quando não apresentavam resultado em água doce receptora ou organismo-modelo. Um estudo do Rio Raritan foi incluído provisoriamente após confirmar no resumo primário amostras de água doce a montante e jusante de quatro estações de tratamento. Essa reconciliação é de avaliadores IA e precisa de validação por especialista.

## O que ainda bloqueia uma revisão final

- Adjudicação dos 149 candidatos atuais por pesquisadores da área; obter resumo ou texto integral para os registros avaliados somente pelo título.
- Resolver por texto integral os 76 casos incertos e validar as decisões provisórias por especialistas.
- A auditoria estratificada das exclusões já cobriu duas amostras de 77 registros. A segunda deixou 27 incertos; as amostras são diagnósticas, não permitem estimar recall global sem ponderação por estrato.
- A busca suplementar OpenAIRE recuperou 278 registros sem correspondência exata no corpus, triados uma vez (174 inclusão provisória, 73 incertos e 31 exclusões). Falta segunda revisão independente, conferência manual de versões e integração deduplicada ao PRISMA.
- CORE e Semantic Scholar não foram consultados por falta de credenciais. OpenAlex foi usado para recuperação de resumos, sem credencial, em buscas de enriquecimento.


A amostra inicial de descartados identificou dois falsos negativos confirmados em estudos com *Daphnia magna*; evidência de publicação e fonte institucional está resumida em `rounds.md`. Isso levou a adicionar indicadores biológicos ao filtro. A matriz corrente e os pareceres por registro estão em `consolidated-adjudication-round3.csv`.
