# Pesquisa: Inovações Agênticas Aplicáveis ao Academic Hunter

**Criado em:** 2026-09-10
**Escopo:** pesquisa externa sobre arquiteturas agênticas de 2026 e o que delas cabe no AH
**Relação:** complementa `docs/landscape-driven-improvements.md` (melhorias vindas dos concorrentes
de SLR) com inovações vindas da **infraestrutura de agentes** — um campo diferente.

---

## 0. O ponto de partida: o AH já tem o desenho, não a implementação

`docs/superpowers/agents/` contém três perfis já especificados, com **tool sets separados**:

| Agente                     | Papel                                                                        | Tools atribuídas                                                                                       |
| -------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| **Orchestrator** (Planner) | Descobre jargão, configura âncoras e pesos. "Nunca executa a busca profunda" | `quick_topic_discovery`, `read_config`, `update_config`, `list_config_history`, `restore_config_by_id` |
| **Hunter** (Executor)      | Roda o engine, explora grafos de citação                                     | `run_search`, `fetch_paper_by_doi`, `explore_citation_graph`, `fetch_multiple_abstracts`               |
| **Synthesizer**            | Lê o relatório, sumariza, exporta para Obsidian                              | `read_latest_report`, `export_to_obsidian`                                                             |

Isso **é** o padrão orchestrator–worker, com separação de privilégios por papel. Mas é apenas
especificação em Markdown: não há enforcement, nem estado compartilhado, nem orquestração real.
Um agente conectado ao MCP hoje vê as **37 tools** — incluindo as que não deveria usar.

Esta pesquisa mapeia o que a infraestrutura agêntica de 2026 oferece para fechar essa lacuna.

---

## 1. Hermes Agent (Nous Research) — o "Kanban" de workers

**O que é:** framework de agentes open source (MIT, fev/2026), da Nous Research. Ultrapassou
140 mil estrelas no GitHub em menos de três meses; segundo o OpenRouter, tornou-se o agente
mais usado do mundo.

**Cinco mecanismos de colaboração**, em ordem crescente de robustez:

| Mecanismo         | Gatilho                  | Escopo                            | Limite                           |
| ----------------- | ------------------------ | --------------------------------- | -------------------------------- |
| `delegate_task`   | tool call                | Dentro de uma sessão              | 3 paralelos, profundidade máx. 2 |
| Mixture of Agents | tool call                | Sessão, multi-modelo              | 4 modelos + 1 agregador          |
| Background Review | contador do sistema      | Sessão, em background             | 1 thread daemon                  |
| `send_message`    | tool call                | Cross-profile, mesmo processo     | —                                |
| **Kanban**        | tick do dispatcher (60s) | **Cross-processo, cross-restart** | limite em tempo real             |

Só o **Kanban** é orquestração real entre processos. Os quatro primeiros rodam num único
processo; sub-agentes não se comunicam entre si e são planos (sem aninhamento).

### 1.1 Arquitetura do Kanban — o que vale copiar

**Board durável em SQLite** (`kanban.db`), com tabelas:

- `tasks` — ID, título, status, prioridade, assignee, tenant, workspace
- `task_links` — dependências pai-filho
- `task_comments` — log de comunicação _append-only_
- `task_events` — trilha de auditoria de **todas** as transições de estado

**Concorrência:** o banco roda em **modo WAL** com transações `BEGIN IMMEDIATE`. O claim de
tarefa usa **compare-and-swap** sobre `tasks.status` e `tasks.claim_lock` — só um escritor
"ganha"; os perdedores veem zero linhas afetadas e pulam. **Sem locks distribuídos.**

**Dispatcher:** loop em background que a cada 60s promove tarefas, **recupera claims órfãos de
workers mortos**, e faz spawn de workers.

**Workers são subprocessos independentes** (`sys.executable -m hermes_cli.main`), recebendo
`HERMES_KANBAN_DB` e `HERMES_KANBAN_BOARD` por ambiente.

**Heartbeat:** o worker precisa chamar `heartbeat_claim` dentro de um timeout, senão seu claim
é recuperado por outro.

**Circuit breaking:** após `BLOCK_RECURRENCE_LIMIT = 2` re-bloqueios, a tarefa é auto-bloqueada
para evitar loops infinitos de desbloquear/rebloquear.

**Máquina de estados:** `triage → todo → scheduled → ready → running → blocked → review → done
→ archived`, com motivos de bloqueio tipados (`dependency`, `needs_input`, `capability`, `transient`).

**Princípio de segurança mais interessante:** workers são identificados por `HERMES_KANBAN_TASK`
e recebem **apenas tools de ciclo de vida** — `kanban_complete`, `kanban_block`,
`kanban_heartbeat`, `kanban_comment`. Eles **não veem** `kanban_list` nem `kanban_unblock`,
o que impede mudanças de estado não autorizadas no board inteiro. Só perfis de orquestrador
têm o toolset completo.

---

## 2. O padrão orchestrator–worker em produção (2026)

Levantamento da literatura de arquitetura de agentes:

**Por que é o padrão default.** Um supervisor decompõe a tarefa e delega a workers
especializados; ele vê o quadro completo, os workers só a sua fatia. O supervisor **não faz
trabalho de domínio** — isso habilita **model tiering**: modelo caro para planejar, baratos
para executar, com **40–70% de economia de custo** reportada.

**Quando usar:** workflows sequenciais bem definidos, que precisam ser previsíveis e
auditáveis, com decomposição em **2–4 papéis especializados** e handoffs claros.

**Variantes:**

- **Supervisor com feedback loop** — monitora saídas dos workers e pode redirecionar, refazer
  ou sobrescrever. Sempre com limite de iteração (~3).
- **Hierárquico** — workers que são eles mesmos orquestradores. Recomendado só acima de 10
  agentes, e **profundidade máxima 2** ("debugging is brutal").
- **Pipeline** — sequência fixa A→B→C. "O padrão mais chato, e frequentemente o mais confiável."
- **Swarm / peer-to-peer** — sem coordenador; mais flexível e o mais difícil de depurar.

**Práticas de produção que a literatura repete:**

- **Comece simples.** Escale para hierarquia só quando um modo de falha _medido_ justificar.
- **Read-parallel, write-single-threaded** (posição de 2026 do time do Devin): sub-agentes
  paralelos **apenas para coleta de informação**, nunca para escrita ou mudança de estado.
- **Checkpoint em cada handoff**, com estado tipado/escopado e histórico append-only imutável.
- **Observabilidade primeiro** — "construa o dashboard antes do agente". Langfuse, LangSmith,
  Inspect AI são os instrumentos citados.
- **Gating de risco** fora do orquestrador, para aprovações e permissões.

**Modos de falha medidos:**

- **Handoffs não validados = ~23,5% das falhas** (dados MAST).
- O orquestrador é dependência crítica: um erro de entendimento cascateia.
- Sistemas multi-agente consomem **~15× os tokens** de um agente único.
- Esgotamento de contexto após 3–4 rodadas; loops sem limite; erros semânticos silenciosos que
  atravessam fronteiras de agente sem código de erro.

---

## 3. Memória de agente — o campo de batalha de 2026

Três arquiteturas concorrentes:

| Arquitetura             | Exemplos             | Trade-off                                                    |
| ----------------------- | -------------------- | ------------------------------------------------------------ |
| **Vetorial / flat RAG** | Mem0                 | Rápido, barato; **sem modelo temporal**                      |
| **Grafo**               | Zep/Graphiti, Cognee | Entidades, relações, janelas de validade temporal; mais caro |
| **Compressão de token** | Headroom             | Reduz prompt (código −79,8%), mas **lossy**                  |

**Números (com ressalva):** no LongMemEval, Zep reporta 71,2% e Mem0 92,5%/94,4%
(auto-reportado), mas na **subtarefa temporal** Zep faz 63,8% contra 49,0% do Mem0.
Zep é o único com paper revisado por pares (arXiv 2501.13956).

**A ressalva importa mais que os números.** A literatura é explícita: quase todos os números
são auto-reportados e contestados. O mesmo sistema pontuou 84%, depois 58,44%, depois 75% na
mesma configuração. E o achado metodológico central:

> "Um número sem judge, sem slice e sem modelo de resposta associado não é um resultado."

Mastra pontuou 84,23% com GPT-4o e 94,87% com GPT-5-mini — **10 pontos de variação sem mudar
nada no sistema**.

**Problema aberto:** nenhum benchmark público testa memória como _mudança comportamental_
(erro → correção capturada → persistida → recorrência medida numa sessão nova). LongMemEval,
LoCoMo, MemBench e MemoryAgentBench testam memória como _recuperação de informação_.

---

## 4. Agentes científicos autônomos — o precedente mais direto

### Robin (FutureHouse) — _Nature_, maio/2026

O achado mais relevante para o AH, porque é **exatamente o domínio**: literatura científica
com agentes coordenados. Robin descobre e valida candidatos terapêuticos num ciclo
lab-in-the-loop, com três agentes especializados:

| Agente     | Função                                                                                |
| ---------- | ------------------------------------------------------------------------------------- |
| **Crow**   | Varre grandes volumes de literatura e produz revisões concisas para achar estratégias |
| **Falcon** | Revisões mais profundas, produz relatórios de avaliação por candidato                 |
| **Finch**  | Analisa dados experimentais, escreve e executa código em notebooks                    |

**Números:** 551 papers analisados em 30 minutos, contra ~294 horas estimadas para um humano
(**~200× de redução**). Identificou alvo, propôs 30 candidatos, validou 2 in vitro. E lançou
**8 trajetórias paralelas de análise com meta-análise por consenso** para lidar com variabilidade.

Esse último ponto ecoa diretamente o achado do EmbedSLR (§ do outro documento): **consenso
entre trajetórias/modelos supera instância única.**

### Outros

- **Co-Scientist** (Google DeepMind) — multi-agente sobre Gemini para hipóteses; validado em
  repurposing de fármacos e resistência antimicrobiana.
- **ERA** (Harvard) — LLM + tree search para gerar software científico.
- **An Agentic AI Scientific Community** — enxame de "labs virtuais", cada um com **planner,
  worker e reviewer**. É o padrão orchestrator–worker aplicado a descoberta.
- **AutoLabs**, **SciAgents**, **AI Scientist-v2**, **Genesis** (robot scientist).

### Desafios que a literatura aponta

1. Benchmarks agênticos que avaliem o **ciclo de decisão completo**, não etapas isoladas;
2. Planejamento nativo de incerteza;
3. Segurança como restrição de primeira classe (LLMs identificam mal riscos de laboratório —
   acurácia abaixo de 75% nos testes citados);
4. Arquiteturas modulares e interoperáveis;
5. Acesso equitativo.

---

## 5. O que isso significa para o AH — inovações concretas

### 5.1 Kanban durável para SLR ⭐ a mais transformadora

**Problema real:** o pipeline do AH é uma execução monolítica. Se falha na 5ª de 7 fontes,
perde-se tudo. Um SLR de verdade leva dias e é interrompido.

**Proposta:** cada (fonte × âncora) vira uma _task_ num board SQLite; workers buscam, com
heartbeat e recuperação de claims órfãos. O estado sobrevive a restart. Um SLR retomável.

**O AH já tem os blocos:** `SQLiteCache`, `MCPDatabaseManager`, `SearchState`. Falta WAL mode,
CAS no claim e o dispatcher.

**Ganho colateral:** resolve de imediato as condições de corrida do dedup (TOCTOU em
`processor.py:19-29` vs `56-60`) — o modelo de claim por CAS elimina a classe inteira de bug.

### 5.2 Enforcement de tool sets por papel

**Problema:** os 3 agentes estão especificados, mas hoje qualquer cliente MCP vê as 37 tools.

**Proposta:** aplicar o princípio do Hermes — worker recebe só as tools do seu ciclo. O
Orchestrator não deveria poder chamar `run_search`; o Hunter não deveria poder reconfigurar;
o Synthesizer não deveria poder buscar.

**Implementação:** já existe infraestrutura em `interfaces/mcp/` (o `decorators.py` morto
inclusive). É sobretudo trabalho de autorização, não de arquitetura nova.

### 5.3 Memória episódica de revisão

**Problema:** o AH não lembra nada entre execuções. Numa revisão contínua (há literatura:
_Continuous SLR_, arXiv 2108.12922), papers já triados são re-triados do zero.

**Proposta:** memória persistente de decisões — "este paper foi excluído, por este critério,
nesta data". Isso é **exatamente** o caso de uso que a literatura diz estar em aberto: memória
como _mudança comportamental_, não recuperação.

**Oportunidade de artigo:** o campo de memória carece de benchmarks de mudança comportamental.
Uma revisão sistemática contínua é um domínio onde isso é mensurável (re-triagem evitada).

### 5.4 Validação de handoff

**Dado:** ~23,5% das falhas em sistemas multi-agente são handoffs não validados.

**Proposta:** validar os contratos entre etapas do AH — busca→triagem→score→export. Hoje o
`enricher.py:73` sobrescreve score sem renormalizar: é um handoff quebrado, exatamente o padrão
que a literatura identifica como falha mais comum.

### 5.5 Consenso de trajetórias

**Precedente duplo:** Robin (8 trajetórias paralelas + meta-análise por consenso) e EmbedSLR
(consenso entre modelos supera modelo único).

**Proposta:** rodar N configurações (pesos/modelos distintos) sobre o mesmo corpus e consolidar
por consenso, em vez de uma execução única. Reaproveita o mecanismo de pesos que já existe, e
casa com a ideia de **ensemble de embeddings** do outro documento.

### 5.6 Observabilidade

O AH não tem nenhuma. A literatura é unânime: observabilidade antes de escala. Para SLR, o
análogo é rastrear por execução: quais fontes retornaram o quê, onde os papers foram perdidos,
quanto tempo por etapa. Boa parte disso já está no `SearchState` — falta expor.

### 5.7 Model tiering (quando o LLM entrar)

Se a Fase 1 do roadmap for implementada, aplicar desde o início: modelo caro para planejar
(geração de query, decisão de inclusão difícil), barato para executar (triagem em lote,
formatação). Economia reportada de 40–70%.

---

## 6. Priorização sugerida

| Ordem | Inovação                          | Esforço | Por quê                                               |
| ----- | --------------------------------- | ------- | ----------------------------------------------------- |
| 1     | **Validação de handoff (5.4)**    | Baixo   | Corrige falha medida; `enricher.py` é o caso concreto |
| 2     | **Observabilidade (5.6)**         | Baixo   | Pré-requisito para medir qualquer outra coisa         |
| 3     | **Tool sets por papel (5.2)**     | Médio   | Já especificado, falta enforcement                    |
| 4     | **Consenso de trajetórias (5.5)** | Médio   | Duplo precedente; reusa o que existe                  |
| 5     | **Kanban durável (5.1)**          | Alto    | Maior ganho estrutural; resolve corridas              |
| 6     | **Memória episódica (5.3)**       | Alto    | Maior potencial de artigo original                    |
| 7     | **Model tiering (5.7)**           | —       | Depende do LLM entrar                                 |

---

## 7. Leituras recomendadas

**Arquitetura de agentes**

- "A Methodology for Selecting and Composing Runtime Architecture Patterns for Production LLM
  Agents" — arXiv 2605.20173 (seis padrões recorrentes)
- Hermes Agent — github.com/NousResearch/hermes-agent (docs de Kanban; DeepWiki tem a
  dissecação de `kanban_db.py` e `kanban_tools.py`)
- Zenith — github.com/Intelligent-Internet/zenith (harness de melhoria contínua via MCP/ACP)

**Agentic RAG**

- SoK: Agentic Retrieval-Augmented Generation — arXiv 2603.07379 (formaliza como POMDP;
  taxonomia de planejamento, orquestração, memória e uso de ferramentas)

**Memória**

- REMem: Reasoning with Episodic Memory in Language Agent — ICLR 2026
- LongMemEval — arXiv 2410.10813
- Zep — arXiv 2501.13956 (o único com revisão por pares na comparação)

**Agentes científicos**

- "A multi-agent system for automating scientific discovery" (Robin) — _Nature_ 655:497–505, 2026
- "An Agentic AI Scientific Community for Automated Neural Operator Discovery" — arXiv 2607.12122
