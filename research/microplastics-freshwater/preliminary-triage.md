# Triagem preliminar da busca de microplásticos em água doce

Execução inicial para a triagem detalhada: `results/run_20261116_155250`, 1.000 por fonte, corte automático original `_kw_score >= 12`. Execução ampliada de sensibilidade: `results/run_20261116_160845`, contexto no título ou resumo e piso 6. Matriz local: `screening_adjudication_preliminary.csv` no diretório daquela execução. O classificador e a revisão de título/resumo foram feitos por IA e são **provisórios**, não substituem adjudicação por pesquisador.

## Resultado da primeira passada

Dos 79 candidatos que passaram ano e âncora, a triagem provisória marcou 76 para possível inclusão, 2 incertos e 1 exclusão. O material analisado inclui títulos, 23 resumos já presentes nos registros e resumos consultados para 8 estudos em fontes bibliográficas. Ainda assim, 48 registros ficaram avaliados somente pelo título.

O corte 12 teria removido 22 candidatos: 20 parecem potencialmente relevantes, um é incerto e um foi excluído. Isso aponta risco de falso negativo elevado para o corte 12. O perfil versionado foi alterado para `_kw_score >= 6`, que preserva os 79 candidatos deste conjunto para revisão humana. A redução do corte é uma medida de recuperação, não evidência de que os 76 provisórios estejam cientificamente incluídos. A comparação do portão de contexto ampliou a matriz para 103 registros (102 acima do piso 6 e 1 abaixo); esses 24 adicionais ainda precisam de triagem individual.

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

## O que ainda bloqueia uma revisão final

- Adjudicação dos 103 candidatos da matriz ampliada por um pesquisador da área; obter resumo ou texto integral para os 48 julgados apenas pelo título.
- Revisar uma amostra estratificada dos 4.685 registros descartados na etapa de ano/âncora/contexto, agora disponível em `screening_exclusions_*.csv`; a triagem dos 79 candidatos não estima falso negativo nesse portão.
- Segunda revisão independente e resolução de discordâncias para estimar concordância.
- Busca ampliada com OpenAlex, Semantic Scholar e CORE quando as chaves forem configuradas. Nenhuma dessas fontes foi consultada nesta sessão.
