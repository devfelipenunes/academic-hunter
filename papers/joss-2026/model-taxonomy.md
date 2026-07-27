# Taxonomia de Modelos para Embedding — Como Referenciar no Paper

**Objetivo:** Entender os tipos de modelo, suas diferenças arquiteturais, e como posicionar o Weight-Bleeding corretamente na literatura.

---

## 1. Classificação por Arquitetura de Modelo

### 1.1 Bi-encoders (Dual Encoders)

**Como funcionam:** Dois encoders (ou um compartilhado) que processam query e documento separadamente, gerando embeddings independentes. Similaridade é calculada via dot product / cosine.

```
Query ──→ Encoder ──→ [emb_q]
                            ╲  dot / cosine
                            ╱
Doc ──→ Encoder ──→ [emb_d]
```

**Prós:** Rápido (embeddings pré-computados), escalável (milhões de docs)
**Contras:** Sem interação query-doc na codificação
**Exemplos:** Sentence-BERT, all-MiniLM-L6-v2, DPR, Contriever
**Nosso uso:** Weight-Bleeding opera em bi-encoders (all-MiniLM-L6-v2)
**Como referenciar:** _"bi-encoder models such as Sentence-BERT [@sentence-transformers]"_

### 1.2 Cross-encoders

**Como funcionam:** Query e documento são concatenados e processados juntos por um único transformer. Produz score de relevância diretamente.

```
[CLS] query [SEP] doc [SEP] ──→ Transformer ──→ relevance score
```

**Prós:** Alta precisão (atenção cruzada entre query e doc)
**Contras:** Lento (precisa processar cada par), não escalável para retrieval
**Exemplos:** ms-marco-MiniLM-L-6-v2, BERT reranker, monoT5
**Nosso uso:** Usamos cross-encoder para validação (Spearman correlation)
**Como referenciar:** _"cross-encoders [@sentence-transformers] provide accurate relevance scoring but do not scale to large candidate sets"_

### 1.3 Decoder-only LLMs (Modelos Causais)

**Como funcionam:** Autoregressivos — cada token só vê tokens anteriores (máscara causal). Tradicionalmente ruins para embeddings por falta de bidirecionalidade.

```
Token₁ → Token₂ → Token₃ → ... → Tokenₙ
         ↑causal  ↑causal        ↑causal
```

**Problema:** Sem contexto bidirecional, embeddings são fracos
**Soluções na literatura:**

- **Echo Embeddings** (Springer 2025): repete input 2× — na segunda passagem, tokens têm contexto completo. Input-level. Alvo: decoders.
- **SGPT** (Muennighoff 2022): weighted mean pooling com pesos posicionais. Pooling-level. Alvo: decoders.
- **LLM2Vec** (2024): fine-tuning com masking causal + next token prediction. Training-level.
  **Como referenciar:** _"decoder-only language models require architectural modifications or input manipulation to produce quality embeddings"_

### 1.4 Encoder-only Models (BERT-like)

**Como funcionam:** Bidirecionais — cada token vê todos os outros (atenção completa). Naturalmente bons para embeddings.

```
Token₁ ↔ Token₂ ↔ Token₃ ↔ ... ↔ Tokenₙ
         ↑bidir    ↑bidir        ↑bidir
```

**Prós:** Embeddings de alta qualidade para tarefas de representação
**Exemplos:** BERT, RoBERTa, all-MiniLM-L6-v2, BGE
**Nosso uso:** all-MiniLM-L6-v2 (bi-encoder baseado em encoder-only)
**Como referenciar:** _"encoder-only models provide bidirectional context, making them natural choices for sentence embedding models"_

---

## 2. Classificação por Estratégia de Ponderação

Esta é a **nossa contribuição** — como controlar o embedding centroid.

| Estratégia          | Nível        | Exemplos                            | Precisa modificar modelo?    |
| ------------------- | ------------ | ----------------------------------- | ---------------------------- |
| **Pooling-weight**  | Pooling      | SGPT (posicional), SIF (frequência) | ✅ Sim                       |
| **Training-weight** | Treinamento  | GRIT, LLM2Vec, fine-tuning          | ✅ Sim (retreino)            |
| **Input-weight**    | Input        | **Weight-Bleeding**, Echo           | ❌ Não (string manipulation) |
| **Post-hoc**        | Pós-encoding | SIF (remoção de componentes)        | ❌ Não                       |

**Nossa vantagem:** Input-level é o único que:

1. Não modifica o modelo (inferência padrão)
2. Não requer retreino
3. É configurável por JSON em tempo real
4. Funciona em qualquer bi-encoder

---

## 3. Como Referenciar no Paper — Sugestões

### Seção Related Work — Estrutura Proposta

**Parágrafo 1 — Bi-encoders para Retrieval:**

> _"Sentence transformers [@sentence-transformers] popularized bi-encoder architectures for semantic search, using mean pooling over token embeddings to produce fixed-size sentence vectors. While efficient, this approach applies uniform weight to all tokens, limiting domain-specific control."_

**Parágrafo 2 — Weighting Methods:**

> _"Several works address this limitation. SGPT [@sgpt2022] proposes weighted mean pooling with position-based weights for decoder-only models. SIF embeddings [@sif2017] weight terms by corpus frequency and remove common components via PCA. Both modify the pooling strategy itself — Weight-Bleeding achieves weighting at the input level without architectural changes."_

**Parágrafo 3 — Term Repetition:**

> _"Echo embeddings [@echo2024] introduce input-level repetition for decoder-only LLMs to overcome causal attention limitations, repeating the entire input and extracting from the second occurrence. Our work differs fundamentally: we target bi-encoders (all-MiniLM-L6-v2), repeat specific terms W times based on domain weights rather than the full text, and aim for configurable weighting rather than attention correction."_

**Parágrafo 4 — SLR Tools:**

> _"ASReview [@asreview2020] uses active learning for screening prioritization but requires labeled data. Our tool operates zero-shot — the researcher defines domain weights and both lexical and semantic scoring adapt without examples."_

### No paper.bib — Sugestão de Novas Referências

```bibtex
@article{llm2vec2024,
  author    = {BehnamGhader, Parishad and Adlakha, Vaibhav and Mosbach, Marius and Bahdanau, Dmitry and Chapados, Nicolas and Reddy, Siva},
  title     = {LLM2Vec: Large Language Models Are Secretly Powerful Text Encoders},
  journal   = {arXiv preprint arXiv:2404.05961},
  year      = {2024},
}

@inproceedings{grit2024,
  author    = {Muennighoff, Niklas and Wang, Liang and Sutawika, Lintang and Roberts, Adam and Biderman, Stella and Le Scao, Teven and Bari, M Saiful and Shen, Sheng and Shen, Zhiqiang and Kostić, Bogdan and others},
  title     = {Generative Representational Instruction Tuning},
  booktitle = {ICLR 2025},
  year      = {2024},
  url       = {https://arxiv.org/abs/2402.09690}
}
```

---

## 4. Nosso Posicionamento na Taxonomia

```
               Embedding Control Methods
                        │
      ┌─────────────────┼─────────────────┐
      │                 │                 │
  Pooling-level    Input-level       Training-level
      │                 │                 │
  ┌───┴───┐       ┌────┴────┐       ┌────┴────┐
  │       │       │         │       │         │
 SGPT   SIF    Echo      WEIGHT-   GRIT    LLM2Vec
 (pos) (freq) (decoder)  BLEEDING  (GRIT)  (fine-tune)
                        (bi-enc.)
                           │
                    ┌──────┴──────┐
                    │             │
              + Lexical      Fused
              Matching      (Lexical + WB)
              (regex)       (70/30 blend)
```

**O que isso significa para o paper:**

- Weight-Bleeding ocupa um **nicho vazio** na taxonomia: input-level + bi-encoder
- Echo é o mais próximo, mas ataca um problema **diferente** (atenção causal em decoders)
- Nossa abordagem é **ortogonal** a SGPT/SIF (podem ser combinadas futuramente)

---

## 5. Terminologia Proposta para o Paper

| Modo de Ablação    | Nome Proposto       | Justificativa                               |
| ------------------ | ------------------- | ------------------------------------------- |
| Só regex           | **Lexical**         | Padrão em IR (vs Semantic/Dense)            |
| Só Weight-Bleeding | **Weight-Bleeding** | Nossa contribuição principal                |
| 70/30 blend        | **Fused**           | Mais preciso que "hybrid" — fusão ponderada |

**Na tabela do paper:**

| Strategy        | Identified | Final   | Top-1 |
| --------------- | ---------- | ------- | ----- |
| Lexical         | 2,886      | 532     | TBD   |
| Weight-Bleeding | 2,986      | 291     | TBD   |
| Fused (ours)    | 2,986      | **501** | TBD   |

---

## 6. Como Melhorar as Referências no Paper

### Problemas Atuais:

1. SGPT referenciado mas sem detalhe do weighted pooling
2. SIF referenciado mas sem explicar a diferença (word-level vs sentence-level)
3. Echo bem referenciado mas pode incluir a citação de que é ICLR 2025
4. Faltam referências sobre: bi-encoder vs cross-encoder trade-off

### Ações:

1. Adicionar no paper.bib: LLM2Vec, GRIT (para mostrar que o campo está ativo)
2. Expandir o parágrafo do Echo para citar o ano (ICLR 2025)
3. Explicitar a diferença decoder-only vs encoder-only na seção de Related Work
4. Adicionar uma nota sobre pooling strategies tradicionais (mean, max, CLS)
