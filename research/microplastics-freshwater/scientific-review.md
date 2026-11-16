# Microplásticos em ecossistemas continentais de água doce

## Síntese científica e estado da revisão

**Data de fechamento desta versão:** 16 de novembro de 2026  
**Tipo de produto:** revisão de escopo assistida por IA, com triagem por título/resumo e síntese narrativa. Não é uma revisão sistemática concluída nem uma meta-análise.

## Pergunta e limites

Esta revisão pergunta como microplásticos e nanoplásticos ocorrem, são transportados e afetam ecossistemas continentais de água doce; quais métodos são usados para detectá-los e quantificá-los; e quais lacunas limitam a comparação entre estudos. O escopo inclui rios, córregos, lagos, reservatórios, wetlands e sedimentos associados, com publicações de 2015 em diante. Estudos exclusivamente marinhos, estuarinos/salobros, de água potável, de efluentes sem ligação explícita a água doce, editoriais e estudos de alimentos sem localização ambiental verificável são mantidos fora da síntese central ou usados apenas como contexto.

As classes de tamanho, unidades, polímeros, matrizes e desenhos experimentais variam muito. Por isso, esta versão não calcula uma concentração global nem combina efeitos em uma estimativa única.

## Busca e seleção

O perfil e o histórico de sensibilidade estão em [`protocol.md`](protocol.md) e [`rounds.md`](rounds.md). A busca principal do projeto usou Crossref, arXiv e DOAJ; CORE e Semantic Scholar não foram consultados por falta de credenciais, e o conector MCP Academic Hunter estava indisponível. APIs públicas sem chave foram usadas para enriquecimento bibliográfico e buscas suplementares. A busca OpenAIRE de 2026 está registrada separadamente; a rodada OpenAlex foi feita em cinco consultas (`microplastic freshwater river`, `microplastic freshwater lake`, `microplastic freshwater ecotoxicity`, `microplastic freshwater analytical methods`, `microplastic freshwater sediment`), com até 100 resultados por consulta, limite de paginação da API ([documentação OpenAlex](https://help.openalex.org/api/paging/)).

| Conjunto | Registros | O que os números significam |
|---|---:|---|
| Matriz local consolidada | 149 | 22 incluídos e 61 incluídos provisoriamente; 39 classificados para contexto; 27 excluídos. A decisão dos 76 casos anteriormente incertos foi baseada em título/resumo; 72 tinham resumo recuperado e 4 permaneceram somente com título. |
| Busca suplementar OpenAIRE | 278 sem correspondência exata local | Triagem inicial: 174 inclusão provisória, 73 incertos e 31 exclusões provisórias. Mantida fora da matriz principal por falta de segunda avaliação independente e reconciliação completa de versões. |
| Busca suplementar OpenAlex | 500 resultados nas consultas; 426 registros únicos; 323 sem correspondência DOI/título exata; 318 após remover cinco duplicatas internas | Triagem de título/resumo: 168 candidatos a estudo primário, 91 itens de contexto/revisão, 41 registros de literatura cinzenta, 15 exclusões e 3 casos para conferir escopo no texto integral. Busca limitada aos 100 primeiros por consulta, não exaustiva. |

Essas contagens vêm de fluxos parcialmente sobrepostos e não devem ser somadas como se fossem registros únicos de um PRISMA final. O arquivo [`candidate-adjudication-round4.csv`](candidate-adjudication-round4.csv) documenta as decisões dos 76 registros; [`openalex-screening-round4.csv`](openalex-screening-round4.csv) e [`openalex-dedup-audit-round4.csv`](openalex-dedup-audit-round4.csv) documentam a triagem suplementar. A adjudicação foi feita por um único avaliador de IA e não substitui revisão especializada.

## Síntese dos achados

### Ocorrência e comparabilidade

Microplásticos foram relatados em rios, lagos, wetlands, sedimentos e organismos de água doce em diferentes regiões. A literatura disponível sustenta ocorrência disseminada, mas não permite ordenar ambientes ou estimar uma abundância global confiável: tamanho mínimo detectável, volume/massa amostrada, malha, digestão, separação por densidade, confirmação espectroscópica, unidades e controles variam entre estudos. Uma revisão de monitoramento em água doce aponta que escolhas de método e faixa de tamanho alteram fortemente as abundâncias reportadas e pede protocolos analíticos comparáveis ([Zhao et al., 2024](https://doi.org/10.1016/j.jhazmat.2024.135329)).

Em rios, a cautela é especialmente importante. Uma avaliação de 36 estudos de campo encontrou ao menos um critério de qualidade sem pontuação em 35 deles, frequentemente por falta de informação sobre tamanho amostral e propriedades físicas/hidráulicas do rio. A abundância reportada variou por cinco ordens de magnitude na água e sete no sedimento, amplitude que mistura diferenças ambientais e metodológicas ([Lofty et al., 2023](https://doi.org/10.1016/j.scitotenv.2022.160893)). Assim, comparar números publicados sem harmonizar métodos pode induzir conclusões falsas sobre “rios mais contaminados”.

### Transporte e destino

O transporte depende da interação entre propriedades das partículas (tamanho, forma, densidade, envelhecimento e biofilme) e condições do sistema (vazão, turbulência, sedimento, matéria orgânica, conectividade e eventos de chuva). Sedimentação, agregação, retenção em margens/leitos e ressuspensão podem alternar o papel de rios e reservatórios entre corredores de transporte e zonas temporárias de retenção. A evidência de campo, contudo, ainda é irregular: poucos estudos acompanham ciclos hidrológicos e reportam as variáveis necessárias para separar transporte de diferenças de amostragem. Uma revisão sobre transporte dinâmico enfatiza a necessidade de passar de ensaios simplificados para hidrologia natural mais complexa ([revisão de transporte, 2024](https://doi.org/10.1016/j.resconrec.2024.107578)).

### Efeitos ecológicos

Ensaios laboratoriais relatam respostas de organismos de água doce, mas efeitos dependem de espécie, tamanho e forma das partículas, polímero/aditivos, dose, duração e desfecho. Muitos estudos experimentais não reproduzem a distribuição de tamanhos, misturas e exposições intermitentes encontradas no ambiente; portanto, resultados laboratoriais demonstram mecanismos e perigos possíveis, mas não quantificam automaticamente risco ecológico em campo.

Um ensaio de mesocosmos em lago boreal expôs comunidades pelágicas por dez semanas a fragmentos de polímeros comuns em uma faixa que incluía concentrações ambientalmente relevantes e observou impactos mínimos sobre a comunidade de zooplâncton nos desfechos avaliados ([Langenfeld et al., 2024](https://doi.org/10.1021/acs.est.4c05327)). Esse resultado restringe generalizações de dano universal em condições ambientais, mas não demonstra ausência de efeitos em outros organismos, habitats, durações ou partículas. Uma revisão sistemática e meta-análise focada em *Daphnia* reuniu 64 estudos e 369 estimativas de reprodução; seus resultados reforçam que os efeitos variam com concentração, duração, temperatura e tamanho de partícula ([meta-análise de 2025](https://pubmed.ncbi.nlm.nih.gov/40920353/)).

### Métodos e qualidade dos dados

Para tornar resultados reproduzíveis, os estudos devem relatar pelo menos: definição e limite inferior de tamanho; matriz, local, data, vazão/condição hidrológica e estratégia de amostragem; massa ou volume processado; materiais e reagentes; brancos de campo e laboratório; recuperação/ensaios de fortificação; digestão e separação; método de identificação do polímero; limites de detecção; e dados brutos com unidades inequívocas. A inspeção visual isolada pode confundir fibras e partículas não plásticas com microplásticos; confirmação química e controles de contaminação são essenciais, sobretudo nas frações menores.

## Conclusões

1. A ocorrência de microplásticos em ecossistemas de água doce está bem estabelecida, mas a magnitude comparativa da contaminação permanece incerta.
2. A heterogeneidade de tamanho mínimo, amostragem, identificação e reporte é uma limitação central; não é defensável sintetizar as concentrações atuais em um único valor global.
3. Transporte e retenção são processos hidrológicos dinâmicos e dependentes do contexto. Mais estudos de campo com hidrologia, sedimentos e conectividade documentados são necessários.
4. Há evidência de efeitos biológicos em experimentos, mas a extrapolação para risco ecossistêmico requer exposições ambientalmente realistas e validação de campo. Um resultado de mesocosmo com efeitos mínimos não pode ser generalizado para todo o ecossistema.
5. As prioridades mais fortes são harmonizar protocolos, ampliar controles de qualidade e confirmação de polímero, incluir frações pequenas/nanoplásticos com limites explícitos, publicar dados brutos e realizar monitoramento longitudinal integrado a variáveis hidrológicas.

## Limitações e o que falta para uma revisão sistemática fechada

- As buscas não cobrem todas as bases bibliográficas especializadas (por exemplo, Web of Science e Scopus não foram consultadas); CORE e Semantic Scholar ficaram indisponíveis sem credenciais.
- A busca OpenAlex foi limitada a 100 resultados por consulta e recuperou somente uma fração dos resultados estimados pela API. OpenAIRE e OpenAlex ainda não foram incorporados por deduplicação completa de versões à matriz principal.
- A triagem ampliada foi feita uma única vez por IA. Não houve duas avaliações humanas independentes nem adjudicação por especialista.
- Ainda falta ler texto integral e extrair, por estudo, desenho, tamanho de amostra, matriz, limite de tamanho, concentração, polímero, QA/QC e resultados. Portanto, os candidatos suplementares não são tratados aqui como estudos confirmados na síntese.
- Não foi feita avaliação formal de risco de viés por estudo, e a busca não foi desenhada para estimar prevalência global ou efeito causal.

**Conclusão de estado:** a versão atual fecha uma revisão de escopo rastreável e uma síntese narrativa útil para orientar o projeto. Para chamá-la de revisão sistemática concluída, ainda é necessário completar busca em bases especializadas, resolver versões/duplicatas, fazer dupla triagem humana e extração de texto integral com avaliação de qualidade.

## Referências centrais

- Zhao, B., Richardson, R. E., & You, F. (2024). *Microplastics monitoring in freshwater systems: A review of global efforts, knowledge gaps, and research priorities*. Journal of Hazardous Materials, 477, 135329. [DOI](https://doi.org/10.1016/j.jhazmat.2024.135329)
- Lofty, J., Ouro, P., & Wilson, C. A. M. E. (2023). *Microplastics in the riverine environment: Meta-analysis and quality criteria for developing robust field sampling procedures*. Science of the Total Environment, 863, 160893. [DOI](https://doi.org/10.1016/j.scitotenv.2022.160893)
- Langenfeld, D. et al. (2024). *Microplastics at Environmentally Relevant Concentrations Had Minimal Impacts on Pelagic Zooplankton Communities in a Large In-Lake Mesocosm Experiment*. Environmental Science & Technology, 58, 19419–19428. [DOI](https://doi.org/10.1021/acs.est.4c05327)
- *Micro- and nanoplastic effects on the reproduction of Daphnia spp. – a meta-analysis* (2025). [PubMed](https://pubmed.ncbi.nlm.nih.gov/40920353/)
- *Dynamic transport of microplastics in aquatic environments: a review* (2024). Resources, Conservation and Recycling. [DOI](https://doi.org/10.1016/j.resconrec.2024.107578)
