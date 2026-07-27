# Weight-Bleeding: Estado da Arte — Comparação com a Literatura

**Projeto:** Academic Hunter / JOSS Paper
**Data:** 21 July 2026
**Autores:** Felipe Nunes

---

## Nossa Contribuição no Contexto do Estado da Arte

| Abordagem                 | Ano         | O que faz                                                           | Modelo                        | Limitação                                                     | Nossa vantagem                                                  |
| ------------------------- | ----------- | ------------------------------------------------------------------- | ----------------------------- | ------------------------------------------------------------- | --------------------------------------------------------------- |
| **Sentence-BERT**         | 2019        | Siamese BERT para gerar sentence embeddings comparáveis             | Bi-encoder (BERT)             | Pooling fixo (mean) sem controle sobre ênfase                 | **+** peso configurável via term repetition                     |
| **SIF Embeddings**        | 2017        | Remove componentes comuns via frequência (Smooth Inverse Frequency) | Word vectors + probabilístico | Só word vectors, não sentence embeddings                      | **+** opera em sentence embeddings de transformers              |
| **SGPT**                  | 2022        | Weighted mean pooling posicional para decoders                      | Decoder LLM (GPT)             | Requer modificar pooling strategy do modelo                   | **+** input-level, sem modificar modelo                         |
| **Echo Embeddings**       | 2025 (ICLR) | Repetir input todo 2× em decoders para bypassar atenção causal      | Decoder-only LLM              | Repetição full-text, sem pesos seletivos                      | **+** repetição seletiva por peso $W$, bi-encoder               |
| **ASReview**              | 2021        | Active learning para priorizar screening em SLR                     | Classificador ML              | Precisa dados rotulados                                       | **+** zero-shot, sem dados de treino                            |
| **BM25 / TF-IDF**         | Clássico    | Sparse retrieval via term frequency                                 | Bag-of-words                  | Sem理解 semântica, sinônimos perdidos                         | **+** captura sinônimos via embeddings                          |
| **Dense Retrieval**       | 2019+       | Embedding-based search via bi-encoders                              | Bi-encoder                    | Centroide genérico sem controle                               | **+** centroide direcionável por pesos                          |
| **Weight-Bleeding (nós)** | 2026        | Term repetition ponderada + $\sqrt{\sigma}$ output scaling          | Bi-encoder all-MiniLM-L6-v2   | Cross-encoder correlation baixa (objetivo: semântico, não QA) | **+** configurável, zero-shot, input-level, sem GPU, não-linear |

---

## Mapa Conceitual

```
                    Embedding Weighting Methods
                              │
            ┌─────────────────┼─────────────────┐
            │                 │                 │
      Pooling-level      Input-level      Training-level
            │                 │                 │
       ┌────┴────┐      ┌────┴────┐       ┌────┴────┐
       │         │      │         │       │         │
     SGPT     SIF   Echo      WEIGHT-   SBERT   GRIT
    (pos)   (freq)  (decoder)  BLEEDING  (bi-   (GRIT)
                              (bi-enc.)  enc)

    Pooling-level: modifica como o modelo agrega tokens
    Input-level: manipula o texto de entrada (nossa categoria)
    Training-level: requer fine-tuning do modelo
```

---

## Análise Detalhada por Abordagem

### 1. Sentence-BERT (2019)

- **Autores:** Reimers & Gurevych
- **Venue:** EMNLP
- **ArXiv:** 1908.10084
- **Ideia:** Usa siamese + triplet networks para gerar sentence embeddings semanticamente significativos a partir de BERT
- **Pooling:** Mean pooling sobre tokens de output (estratégia fixa)
- **Limitação:** O pooling mean trata todos os tokens igualmente — não há como enfatizar termos específicos do domínio
- **Nossa diferença:** Weight-Bleeding ainda usa mean pooling, mas a repetição de termos no input faz o pooling naturalmente dar mais peso aos termos relevantes

### 2. SIF Embeddings (2017)

- **Autores:** Arora, Liang & Ma
- **Venue:** ICLR
- **Ideia:** Remove o componente comum (primeiro componente PCA) de word embeddings e pondera por frequência (a / (a + p(w)))
- **Tipo:** Probabilístico + word-level
- **Limitação:** Opera em word embeddings, não sentence embeddings de transformers
- **Nossa diferença:** Fazemos weighting no input (string manipulation), não via pós-processamento estatístico

### 3. SGPT (2022)

- **Autores:** Muennighoff
- **Venue:** EMNLP Industry
- **Ideia:** Usa decoders (GPT) para sentence embeddings via weighted mean pooling com pesos posicionais
- **Pooling:** Weighted mean pooling (modifica a arquitetura)
- **Limitação:** Requer modificar a estratégia de pooling do modelo; específico para decoders
- **Nossa diferença:** Não modificamos pooling — a manipulação é no texto de entrada, funciona em qualquer bi-encoder

### 4. Echo Embeddings (2025)

- **Autores:** Springer, Kotha, Fried, Neubig, Raghunathan
- **Venue:** ICLR 2025
- **ArXiv:** 2402.15449
- **Ideia:** Repetir o input inteiro 2× em decoder-only LLMs; extrai embeddings da segunda ocorrência (que já viu todos os tokens)
- **Tipo:** Input augmentation (repetição full-text)
- **Diferença fundamental:**
  - **Echo:** repete o **texto inteiro** (todo o input) — sem pesos, sem seletividade
  - **Echo:** alvo = **decoder-only LLMs** (resolver atenção causal)
  - **Echo:** objetivo = **correção de atenção**, não ponderação
  - **Nós:** repetimos **termos específicos** $W$ vezes baseado em pesos de domínio
  - **Nós:** alvo = **bi-encoders** (all-MiniLM-L6-v2)
  - **Nós:** objetivo = **ponderação semântica configurável**

### 5. ASReview (2021)

- **Autores:** van de Schoot et al.
- **Venue:** Nature Machine Intelligence
- **Ideia:** Active learning para priorizar screening: modelo treina iterativamente com labels do revisor
- **Tipo:** Classificador supervisionado
- **Limitação:** Precisa de dados rotulados — o revisor precisa classificar dezenas de papers para o modelo começar a funcionar
- **Nossa diferença:** Totalmente zero-shot — o pesquisador define pesos no config.json e os scores se adaptam sem nenhum labeled example

---

## Síntese: Por que Weight-Bleeding é Original?

**Input-level term repetition em bi-encoders é a contribuição chave.** Nenhum trabalho anterior faz:

1. **Repetição seletiva de termos** baseada em pesos de domínio (Echo repete tudo)
2. **Em bi-encoders** (Echo/SGPT focam em decoders)
3. **Sem modificar pooling** (SGPT/SIF modificam pooling)
4. **Configurável por JSON** sem retreino (diferente de ASReview)
5. **Zero-shot** (diferente de ASReview)

**Fórmula da contribuição:**

$$v_{bleeding} = \frac{N}{N+W} \cdot v + \frac{W}{N+W} \cdot e_t$$

Onde $W$ controla o quanto o centroide "sangra" em direção ao termo alvo.

---

## Próximos Passos na Pesquisa

1. [x] Aguardar resultados do ablation study (keyword vs weight-bleeding vs fused)
   - [x] Verificar se o bug de duplicate resolution foi corrigido
   - [x] Comparar top-1 scores reais de cada modo
   - [x] Re-run com sqrt output scaling para novos números
2. [x] Refinar terminologia: Lexical / Weight-Bleeding / Fused
3. [ ] Fortalecer defesa do cross-encoder validation
4. [ ] Documentar a intencionalidade do centroid shift
5. [x] Corrigir tabelas do paper com dados reais
6. [x] Implementar $\sqrt{\sigma}$ output scaling para resolver compressão da cosine similarity
7. [ ] Explorar transforms configuráveis (sigmoid, cube root) como opção de usuário
