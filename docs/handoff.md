# Handoff — finalizar o Academic Hunter

Documento de passagem de bastão. **Leia isto primeiro** ao retomar o trabalho numa
sessão nova; os detalhes de cada item estão nos commits e no plano.

Última atualização: **2026-09-10**.

---

## Onde o trabalho está

|              |                                                                                         |
| ------------ | --------------------------------------------------------------------------------------- |
| Branch       | `feat/finalizar-ah` — **37 commits à frente de `main`**, que segue intacta em `ffbbc47` |
| Testes       | **901 passando** (`./venv/bin/python -m pytest tests/ -q`, ~2 min)                      |
| Working tree | limpo — o full-text (fases D e E) e os seis defeitos estão commitados                   |
| Planos       | `~/.claude/plans/continue-flickering-catmull.md` (fases D e E)                          |

A flaky do MCP (`test_server_integration.py::test_list_tools`) passa isolada em
22 s e falha sob carga: o servidor leva 44,6 s para o `initialize` contra um
`timeout=45` (medido, ver achados). Ela passou nas últimas execuções.

**Nada foi enviado ao GitHub.** A branch nunca teve upstream; `main` e
`feat/weight-bleeding` são as únicas no remoto.

O objetivo acordado é **deixar a aplicação completa e funcionando perfeitamente**,
antes de voltar aos papers. LLM/SLM **só como experimento**, nunca no pipeline.
Fase 3 do roadmap (frentes de pesquisa) está fora do escopo.

### Comandos deste ambiente

- Python do projeto: `./venv/bin/python` — **`python` não existe** neste shell.
- Suíte: `./venv/bin/python -m pytest tests/ -q` (~3 min).
- Arquitetura: `./venv/bin/python -m pytest tests/test_architecture.py -q` —
  reprova qualquer import de `core/` para `interfaces/`, `app/` ou `plugins/`.

---

## O que já está feito

Fase 0 do roadmap fechada (0.1 score unificado, 0.2 enricher, 0.3 avaliação
rotulada, 0.4 fronteiras hexagonais, 0.5 robustez), mais a camada de escrita,
a correção da fusão do score, a coleção julgada em dois tópicos, métricas de
custo, cache de embedding e o ranking por consulta com BM25.

Cross-encoder (item 2 abaixo) também fechado: `core/nlp/model_cache.py` cacheia
os modelos que sete call sites recriavam a cada chamada, e
`core/nlp/reranker.py` + `RecomputeRanksStep._apply_rerank` implementam o estágio
opt-in de reranking. Medido — e ele **ganha**, ao contrário do embedding.

**Full-text completo (fases A–E)**: portas, chunker, adaptadores (Unpaywall,
Europe PMC, pypdf, cache), `IngestFullTextStep` opt-in, as três tools MCP
(`fulltext_status`, `index_fulltext`, `chunk_search`) e a avaliação na coleção
julgada. Medido e com a base declarada junto: retrieval por trecho ganha
`+0,0764` de nDCG@10 do BM25, sobre 5 das 11 consultas, 16 documentos e um
tópico só. Cobertura 19/108, com teto estrutural de 66%/90% porque 25 dos 108
documentos julgados não têm DOI. Detalhes no item 1 de "O que falta".

**E uma auditoria de código inteira**, que não estava no plano e acabou sendo a
maior parte do trabalho: ~15 defeitos reais corrigidos, cada um com teste que
verifica ter falhado no código anterior. Os de maior gravidade: a **chave do
Semantic Scholar sendo devolvida ao cliente MCP** em toda chamada de
`read_config`; `print()` escrevendo **no canal JSON-RPC** (o transporte é stdio,
onde stdout é o protocolo); `export_report` e `index_papers` **nunca
funcionando**; o **CI vermelho** por falta de `pytest-asyncio` (188 testes async
não rodavam); e o **event loop do servidor bloqueado** por minutos durante um
`run_search`.

Rode `git log --oneline main..feat/finalizar-ah` para a lista.

---

## O que falta

Em ordem de execução sugerida.

### 1. Full-text — **fechado nas fases A–E**; falta ampliar a base da medição

As três tools MCP existem (`fulltext_status`, `index_fulltext`, `chunk_search`),
a identidade do paper viaja na metadata do chunk, a ingestão virou núcleo
compartilhado (`core/fulltext/ingest.py`) e o passo rodou dentro de um run real.

O que a avaliação mediu, e o que ela **não** sustenta: retrieval por trecho ganha
`+0,0764` de nDCG@10 sobre BM25 (0,4801 → 0,5565), mas sobre **5 das 11
consultas, 16 documentos candidatos e um tópico só**. As seis consultas de
`genre_analysis` ficaram de fora — apenas 3 dos 58 documentos daquele pool têm
chunk. Cobertura: 19 dos 108 julgados, 737 chunks.

Três caminhos para ampliar a base, em ordem de retorno:

- **(a) Ampliar a coleção julgada** com documentos que tenham DOI. Continua sendo
  o gargalo humano (item 1 das pendências do autor) e é o que destrava tudo.
- **(b) Melhorar o adaptador** para o caso "a cópia aberta é só uma landing
  page". `fulltext_coverage.json` guarda o motivo de cada falha em `error` —
  comece por ler isso em vez de refazer a rede. Dos 83 documentos endereçáveis,
  29 falharam, e a maioria é isso ou editora recusando cliente que não seja
  navegador.
- **(c) Julgar necessidades específicas** ("qual dataset usaram", "quantos
  anotadores codificaram"). É onde o retrieval por trecho deveria ganhar de
  verdade, e o qrels atual não olha para lá: ele julga relevância tópica, que é
  exatamente o que um abstract já resume bem. Sem isso, um resultado nulo seria
  limitação da coleção para esta pergunta, não veredito sobre a técnica.

### 2. Defeitos menores da auditoria — **fechados**

Os seis que estavam em aberto foram corrigidos, cada um com teste que falha no
código anterior: backoff em 5xx e erro de rede nos conectores, `blocked_sources`
limpo a cada run, escape em BibTeX/RIS/Obsidian, escrita atômica do
`run_stats_*.json`, log no `except` do cache, e o nome do Semantic Scholar vindo
de um lugar só. Detalhes no `CHANGELOG`.

Dois achados colaterais valem registro: o teste que cobria a corrupção do cache
era **vacuoso** (corrompia só o arquivo principal e o SQLite recuperava o banco
pelo `-wal`, então o ramo de erro nunca era alcançado — há um teste-guarda agora),
e o `identified` do Semantic Scholar só afetava a contagem, não a detecção de
peer review, porque `PaperResolver` normaliza o nome antes de procurar o conector.

### 3. Ensemble de embeddings (item 2.2)

`papers/experiments/benchmark_baselines.py` já testa MiniLM, BGE-base e GTE-small
— falta o passo de **combinar em vez de comparar**. Medir na coleção julgada.

### 4. Estabilizar os testes de integração do MCP

`tests/interfaces/mcp/test_server_integration.py` é **flaky**: `test_list_tools` e
`test_server_initialize` falham e passam em execuções alternadas, com
`subprocess.TimeoutExpired` após 45 s. Confirmado em cinco execuções. Suíte
instável contradiz "funcionando perfeitamente".

**A causa está medida.** O servidor MCP leva **44,6 s** para responder ao
`initialize` no `main` — medido num worktree limpo do HEAD, sem nenhuma mudança
desta sessão — contra `timeout=45` no teste. O import do módulo custa 1,9 s, logo
o custo está no startup, não no import. Não é falha de protocolo: com o stdin
aberto a tempo, o servidor responde corretamente aos dois pedidos (ids 1 e 2).
É uma corrida contra o relógio, e qualquer variação de carga decide o resultado.
**Portanto: reduzir o startup ou subir o timeout — não mexer no teste**, que está
correto ao exigir resposta.

### 5. Tag de release

Decisão tomada: **3.0.0**. As mudanças incluem remoção do entry point
`academic-hunter` e movimentação de `core/engine/` para `app/`, o que sob SemVer
pede major. `CITATION.cff` já está no lugar, com a versão casada em `__version__`
(hoje `2.1.0`) — **suba os dois juntos** ou eles divergem.

### 6. Conectores (item 2.4)

Medir contribuição marginal por fonte em vários tópicos e desativar por padrão as
que não pagam o custo. Ver a correção do diagnóstico no `docs/roadmap.md` §2.5:
o flag `is_keyword_only` **não** separa quem contribui de quem não contribui.

### 7. O catálogo de tools do site está incompleto

`docs/mcp/index.html` documenta **21 das 44** tools e `docs/index.html` destaca 18
numa lista curada. As três de full-text entraram e as duas páginas ficaram
internamente consistentes, mas a distância entre o que o servidor registra e o
que o site documenta continua — e já existia antes (eram 18 de 41). Fechar isso
é escrever ~23 cards; a página do MCP diz explicitamente que documenta as
principais, então nada ali mente, mas é a maior lacuna de documentação do
projeto hoje.

---

## Achados que não podem ser re-descobertos

Custaram caro e estão registrados aqui para não se repetirem.

**BM25 supera todo o aparato semântico.** Medido na coleção julgada (108
documentos, 11 consultas, nDCG@10): `bm25` **0,6728** · `keyword` 0,3364 ·
`weighted_norm` 0,3223 · `rank_geometric` 0,2012 · `embedding` 0,1991. E o
embedding custa **~1,5 s por documento** contra 0,006 ms do BM25. Somar o
embedding ao BM25 **piora** monotonicamente com o peso.

**A fusão por ranks percentis destruía informação.** A regra antiga media pior que
cada um dos seus próprios componentes. Substituída por soma ponderada de scores
min-max normalizados.

**A ablation de três modos deixou de medir os modos.** O modo atua no ingest; o
`Relevance_Score` reportado vem de uma fusão independente do modo. `Final` e os
top-scores são iguais por construção — a Tabela 2 do paper de conferência e o
parágrafo de ablation do JOSS estão medindo variação de fonte entre execuções.

**Nunca selecionar o pool de avaliação pela métrica sob teste.** Restringe a
amplitude da variável e a faz parecer pior. A primeira versão do pool usava só o
top-30 por score e o baseline de citações "venceu". Há teste de regressão.

**`Paper.__init__` copia apenas as 14 chaves de `FIELD_SCHEMA`** — passar campos
com `_` ao construtor os descarta em silêncio. Atribuir depois da construção.

**Verificar todo teste de regressão contra o código antigo.** Três testes escritos
nesta sessão passavam no código defeituoso e precisaram ser reescritos. Um teste
que não falha no bug não é teste de regressão.

**`config.json` é reescrito pelo `run_ablation.py`** (precisa, para fixar o modo).
O `save()` escreve as 7 chaves que o arquivo tem, então não há perda, mas rodar a
ablation mexe na config viva.

**`pgrep -f <padrão>` casa com o próprio shell que espera.** Um loop
`until ! pgrep -f run_ablation` nunca termina, porque a linha de comando do shell
contém o padrão.

**O cross-encoder ganha onde o embedding perde — e a diferença é grande.**
Medido na coleção julgada (`papers/experiments/rerank_eval.py`, artefato em
`results/rerank_eval.json`), nDCG@10: `bm25` 0,6728 → `rerank@20` **0,7668** →
oráculo do pool inteiro 0,7916. nDCG@5: 0,6459 → 0,8007. MRR: 0,9394 → 1,0000.
Ganha **nos dois tópicos** (+0,1544 e +0,0436), e o top-20 já captura 97% do teto.
Contraste direto com o embedding de bi-encoder, que _reduz_ o nDCG do BM25
monotonicamente com o peso. Os dois sinais são da mesma família "semântica" e
mesmo assim se comportam em direções opostas: só a medição separa.

**O teste do cross-encoder no MCP era vácuo — e o alvo do patch era o motivo.**
`patch("sentence_transformers.cross_encoder.CrossEncoder")` **não** intercepta
`from sentence_transformers import CrossEncoder`; o atributo do pacote continua
ligado à classe real. Verificado isoladamente. O teste carregava o modelo real
(~25 s) e passava de todo modo, porque tanto o caminho de sucesso quanto o
`except` deixam `"Paper A" in result` verdadeiro. O alvo correto é
`sentence_transformers.CrossEncoder`. Vale conferir todo patch de terceiro que
mire um submódulo enquanto o código importa do pacote.

**A flaky do `test_server_integration.py` é uma corrida contra o timeout, e a
causa está medida.** O servidor MCP leva **44,6 s** para responder ao
`initialize` no `main` (medido em worktree limpo, sem nenhuma mudança desta
sessão), contra um `timeout=45` no teste. O import do módulo custa 1,9 s — o
resto é startup. Não é falha de protocolo: com o stdin fechado a tempo, o
servidor responde corretamente (ids 1 e 2). Qualquer variação de carga decide o
resultado. A correção é reduzir o startup ou subir o timeout, não mexer no teste.

**`Relevance_Score` é arredondado a 1 casa, e isso invalida o reranking
ingênuo.** `steps.py` escreve `round(score, 1)` numa escala 0–10 e todo o
downstream ordena pelo valor **arredondado**. Devolver as notas dos candidatos
na ordem nova preserva o multiconjunto e perde a ordem: duas notas 7,24 e 7,21
colidem em 7,2 e o `sorted` estável volta à ordem de inserção. O ranqueamento
base já produz só 14–19 valores distintos num top-20. A regra que funciona
constrói a ordem na resolução de exportação (`rerank_scores`). Há teste
específico que falha na regra ingênua.

**A `score_precision` era ignorada ali — corrigido.** O `steps.py` arredondava
`Relevance_Score` para 1 casa fixo, embora a setting exista e seja respeitada em
`core/nlp/scorer.py` e nos validators. O rerank tornou a divergência
_load-bearing_: `rerank_scores` constrói a rede **na** precisão em que o score é
escrito, e uma rede mais fina que o arredondamento seria apagada levando a ordem
junto. Agora um único `_score_decimals` alimenta os dois.

**Uma revisão de qualidade pegou duas coisas que a medição não pegaria.** Vale
registrar porque são da mesma família — código que afirma uma coisa e faz outra:

- O script de medição gravava `remap_rule: "... see reranker.rerank_scores"` no
  artefato **sem nunca chamar `rerank_scores`**; fazia um `sorted(head) + tail`
  próprio. Os números por acaso coincidiam (a regra redistribui os scores
  preservando a ordem do cross-encoder), mas a proveniência apontava para código
  não exercitado. Ao consertar, o `Timing` do projeto se revelou a abstração
  certa — a docstring dele já dizia contar pares `(query, documento)`, e eu havia
  escrito o contrário para justificar não usá-lo.
- `settings.rerank.enabled` usava `bool(...)`, e **`bool("false")` é `True`** — um
  `"enabled": "false"` escrito como string ligava o estágio. Agora só um booleano
  real habilita.
- E o estágio contava como reranqueado o que não foi: quando a faixa de scores é
  estreita demais para a rede, `rerank_scores` abstém e devolve tudo intacto, mas
  `stats["reranked"]` e os diagnósticos já tinham sido gravados. Agora o contador
  conta o que **mudou** e os diagnósticos registram o que o cross-encoder **disse**
  — dois fatos distintos, ambos verdadeiros.

**O PMC não entrega PDF a cliente que não seja navegador.** Medido:
`pmc.ncbi.nlm.nih.gov/…/pdf/` responde **200 com HTML**. Qualquer plano de
"raspar o PDF do PMC" não funciona. O que funciona é a API do **Europe PMC**
(`/europepmc/webservices/rest/{pmcid}/fullTextXML`), que serve os mesmos artigos
em JATS XML — e é melhor que PDF, porque o XML já traz as seções marcadas, que é
justamente o que o chunker teria de adivinhar por heurística de cabeçalho.
Este documento afirmava o contrário antes de a medição ser feita.

**O `best_oa_location` do Unpaywall não é o lugar de onde baixar.** Ele é a
escolha por _confiabilidade_, e com frequência é a landing page da editora com
`url_for_pdf` nulo — enquanto **outro** local do mesmo registro nomeia o PDF.
Usar só o "melhor" transformava "há um PDF no repositório" em "o download
falhou". Vale para qualquer consumidor da API do Unpaywall.

**Medir `AcademicHunter()` exige cuidado, e eu errei duas vezes.** A primeira
medição deu 7,7 ms (com um config mínimo) e a segunda 1 ms (contaminada por cache
de um warmup). O valor real, com o config do projeto e sem cache, é **169 ms** —
vinte vezes o primeiro número. A conclusão que eu havia tirado disso ("não vale
corrigir") estava errada. Aquecimento e config de teste são as duas formas
fáceis de medir a coisa errada aqui.

**Bytecode obsoleto faz um teste de regressão mentir.** Ao reverter uma correção
para conferir que o teste a pega, o `.pyc` fica com o mesmo mtime (mesmo segundo)
do `.py` restaurado e o Python segue usando a versão compilada — o experimento
então dá verde com o código defeituoso. **Limpe `__pycache__` antes de cada
reversão**, ou o resultado não significa nada.

---

**O teto de cobertura de full text é dos DADOS, não do código.** 25 dos 108
documentos julgados **não têm DOI nenhum**, então nenhum sistema de full text
conseguiria alcançá-los. O teto por tópico é 65,5% (`genre_analysis`) e 90,0%
(`blockchain_governance`). Consequência metodológica: exigir cobertura de 100%
do pool para uma consulta entrar na comparação produz **subconjunto vazio** — a
regra correta é restringir o conjunto de candidatos a `pool ∩ documentos com
chunk` e fazer **todas** as estratégias ranquearem esse mesmo conjunto. Isso não
é o erro do pool top-30: lá a restrição vinha da métrica sob teste; aqui vem de
um fato exógeno. Regra geral: medir o teto estrutural **antes** de definir o
critério de comparabilidade.

**`download_failed` cobria três situações e o "porquê" se perdia.** (a) erro
transitório de rede, (b) a cópia em acesso aberto é só uma landing page — o
Unpaywall diz `is_oa=True` mas o único local não nomeia PDF, então o download
devolve HTML, (c) a editora recusa cliente que não seja navegador. Só (a) vale
retentar; (b) pede outro adaptador; (c) nunca vai funcionar. Agora
`_full_text_error` guarda a mensagem por documento e o artefato de cobertura a
carrega. **Não é teoria: uma segunda passada recuperou um documento** que havia
falhado na primeira.

**`force` apagava os chunks antes de buscar.** Medido ao rodar `force` em três
papers: os sete chunks que o índice tinha foram removidos e a nova busca falhou
em dois deles — o documento ficou sem nada. A substituição agora é apagar e
gravar juntas, **depois** de o texto estar em mãos. Um `force` que falha deixa o
índice como estava.

**`no_text_layer` juntava duas coisas.** "PDF escaneado" (o conserto é OCR) e
"texto extraído mas nenhuma seção reconhecível" (o conserto é o extrator) iam
para o mesmo status. Agora o segundo é `no_sections`. Apareceu num run real: dois
documentos passaram pelo teste de camada de texto e só um foi indexado.

**Os agradecimentos envenenam o retrieval, e isso foi medido.** Numa consulta
sobre o próprio assunto de um paper, a seção de agradecimentos apareceu em
**dois dos três primeiros lugares** — lista de autores, financiadores e conflito
de interesses. Entraram em `_DROPPED_BY_DEFAULT` junto de `references` e
`appendix`, pelo motivo que o plano já dava para eles.

**`load_documents` descartava o DOI.** O carregador compartilhado dos
experimentos (`papers/experiments/retrieval_eval.py`) projeta cada documento
julgado numa forma fixa e não incluía o `DOI`, embora o qrels o tenha embutido.
O primeiro run do full-text reportou `no_doi: 108` numa coleção com 83 DOIs — um
erro que se parece com um resultado. Campo adicionado ao `shape()`.

**Ordenar artefatos por `ctime` é frágil, e um teste piorava isso.** Em Linux
`ctime` é hora de mudança de metadado, não de criação. Pior: `test_pipeline.py`
construía `AcademicHunter` sem `output_dir` e gravava
`run_stats_test_stats.json` **dentro de `results/`** a cada execução da suíte;
sem carimbo no nome, ele ganhava por ctime e virava "o último run" — o
`fulltext_status` chegou a imprimir `Last run: results`. Correção: a seleção usa
o carimbo `(\d{8}_\d{6})` do próprio nome do arquivo (um arquivo sem carimbo
nunca ganha), e o teste ganhou `output_dir` em `tempfile.mkdtemp()`. Vale grepar
`AcademicHunter(` sem `output_dir` em `tests/` — havia 8 ocorrências.

---

## Decisões já tomadas (não reabrir sem motivo)

| Decisão                    | Escolha                                                            |
| -------------------------- | ------------------------------------------------------------------ |
| CLI                        | Removido; o MCP é a única interface                                |
| LLM/SLM                    | Só como experimento, nunca no pipeline                             |
| Fase 3 (pesquisa)          | Fora do escopo                                                     |
| Anotação da coleção        | Eu rotulo, o autor do projeto revisa — **revisão ainda pendente**  |
| Versão da release          | 3.0.0                                                              |
| Biblioteca de PDF          | `pypdf` (o PyMuPDF do roadmap é AGPL)                              |
| Reranking                  | Opt-in por `settings.rerank`, **desligado por padrão**             |
| Reranking sem query        | Não atua: o cross-encoder pontua o par (query, documento)          |
| Full-text                  | Opt-in por `settings.fulltext.enabled`, **desligado por padrão**   |
| Biblioteca de PDF          | `pypdf` no extra `fulltext` (o PyMuPDF do roadmap é AGPL)          |
| Chunk                      | 180 palavras com 40 de sobreposição — imposto pelo MiniLM (256 wp) |
| Coleção de chunks          | `paper_chunks`, separada (o ChromaDB não tem `$exists`)            |
| OCR                        | Não: tesseract não é dependência e quebraria o custo zero          |
| Fontes de full-text        | Unpaywall → Europe PMC, encadeadas                                 |
| Chunk carrega a identidade | `title`/`doi`/`year`/`source` na metadata (a coleção estava vazia) |
| Seções descartadas         | `references`, `appendix` **e `acknowledgements`** (medido)         |
| Status de texto            | `no_text_layer` (sem texto) ≠ `no_sections` (texto sem seções)     |
| `force`                    | Apaga e grava juntos, só depois do texto em mãos                   |
| Coleção da avaliação       | `paper_chunks_eval`, em banco próprio, longe do `chunk_search`     |
| Fragmento de página        | Não existe: o PDF tem páginas, o JATS do Europe PMC não tem        |

---

## Pendências que dependem do autor do projeto

1. **Revisar os 598 julgamentos** da coleção. São meus, por leitura de título e
   abstract, de anotador único, sem medida de concordância. As conclusões só valem
   na medida em que as etiquetas valem, e o README da avaliação registra isso.
2. ~~**Rotacionar a chave do Semantic Scholar.**~~ **Revogado por medição:** a
   auditoria buscou o valor em todos os blobs (`git rev-list --all`) e **a chave
   nunca esteve no histórico**. Os `config.json` antigos tinham `""`, e o único
   achado é uma chave falsa de teste. O que existia de verdade era outro
   vazamento — `read_config` devolvendo a chave ao cliente MCP — e esse está
   corrigido.
3. **Revisar os papers** — adiado por decisão. A Tabela 2 do paper de conferência
   e o parágrafo de ablation do JOSS precisam de atenção (ver achados acima).
4. **Decidir se liga o reranking.** A medição recomenda: ganha nos dois tópicos,
   +0,0940 de nDCG@10 no top-20. O default do _produto_ continua `false` porque
   `sentence-transformers` é o extra opcional `ml` (~2 GB) e um default ligado
   faria a instalação mínima falhar em silêncio. Ligar é uma linha no
   `config.json` local: `"rerank": {"enabled": true}`, junto de um
   `ranking_query` — sem query o estágio avisa e não atua.
5. **Decidir se liga o full-text.** O passo **já rodou dentro de um run real**
   nesta sessão (40 papers incluídos, 2 tentados, `stats["full_text"]` e as
   colunas no CSV conferidos) — o que faltava de verificação está feito. Ligar é
   `settings.fulltext.enabled: true` mais um `email` no bloco `fulltext` (ou nem
   isso: o Europe PMC dispensa endereço). Requer o extra `fulltext`
   (`pip install academic-hunter[fulltext]`) — que **está instalado neste venv**,
   mas não é dependência padrão do pacote.
6. **Decidir o que fazer com a cobertura baixa de full text (19/108).** As duas
   alavancas estão no item 1 de "O que falta": ampliar a coleção julgada com
   documentos que tenham DOI, e melhorar o adaptador para os casos cujo motivo
   está registrado em `error` no `fulltext_coverage.json`.
