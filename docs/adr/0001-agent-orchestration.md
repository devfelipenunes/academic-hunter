# ADR 0001: Manter a orquestração científica no núcleo do Academic Hunter

- **Status:** aceito
- **Data:** 2026-11-16

## Contexto

O Academic Hunter já separa regras científicas e pipeline das interfaces usando portas e adaptadores. MCP permite que clientes compatíveis chamem as ferramentas sem acoplar o núcleo a um framework de agentes. O projeto também possui busca semântica, Chroma, indexação de texto integral em chunks, recuperação de passagens, exportação e um pipeline determinístico.

O problema imediato é melhorar a qualidade e a rastreabilidade da evidência recuperada e avaliá-la em corpus científicos. Adotar uma segunda camada de agentes antes de medir esses resultados aumentaria dependências e duplicaria fluxo sem provar benefício.

## Decisão

- Não adicionar LangChain nem LangGraph como dependência do núcleo.
- Manter o pipeline de busca e triagem determinístico e acessível via MCP.
- Permitir integrações opcionais em adaptadores ou exemplos externos. LangChain pode consumir as ferramentas MCP; o núcleo não deve depender dele.
- Considerar LangGraph para um adaptador de workflow separado se o produto passar a exigir execuções longas que persistam estado, pausem para revisão humana e retomem após falhas.
- Se esse adaptador for criado, preservar o estado auditável da revisão (fontes, consulta, versão, decisão, revisor e evidência) fora do contexto conversacional e exigir confirmação humana para decisões de inclusão/exclusão.

## Consequências

O primeiro investimento fica em recuperação citável, paginação de evidência e avaliação reproduzível. Um workflow com checkpoint poderá ser adicionado sem migrar conectores, domínio ou pipeline.

## Condições para reabrir a decisão

Reabrir quando houver requisito concreto de uma revisão que precise pausar entre etapas por dias, aguardar um ou mais revisores, recuperar execução após falha e manter a trilha de auditoria durante a retomada. A necessidade de um chatbot ou uma resposta RAG isolada, sozinha, não justifica LangGraph.
