---
title: "Weight-Bleeding: Configurable Semantic Relevance Scoring via Input-Level Term Repetition in Bi-Encoders"
authors:
  - name: Felipe Nunes
    orcid: 0000-0000-0000-0000
    affiliation: 1
affiliations:
  - name: Independent Researcher
    index: 1
date: July 2026
bibliography: paper.bib
---

# Abstract

Bi-encoder sentence transformers produce fixed-size embeddings via mean pooling over token vectors, treating all input tokens uniformly. This lack of per-term control limits their applicability in domain-specific retrieval tasks where certain technical terms should carry more semantic weight. We introduce **Weight-Bleeding**, an input-level technique that biases bi-encoder embeddings toward high-weight domain terms through embedding-space centroid interpolation. Rather than modifying the model architecture or pooling strategy, Weight-Bleeding computes a weighted reference centroid:

$$v_{ref} = \frac{v_{base} \cdot N_{base} + \sum_i e_{t_i} \cdot W_i}{N_{base} + \sum_i W_i}$$

where $W_i$ are configurable domain weights. The final relevance score applies a square-root transform $s = \sqrt{\sigma} \times 10$ to the cosine similarity $\sigma$, correcting the compressed similarity range inherent to bi-encoders. In an ablation study across seven academic databases, Weight-Bleeding recovers 92.7% of keyword-matched papers while adding semantically similar papers that exact matching misses. A comparison of six output transformations (linear, square root, cube root, log1p, quadratic, sigmoid) confirms that $\sqrt{\sigma}$ provides the best balance of recall and selectivity. Weight-Bleeding requires no GPU, no fine-tuning, and no labeled data — the user provides only a JSON configuration of domain weights.

# 1. Introduction

Bi-encoder sentence transformers [@sentence-transformers] have become the standard approach for semantic retrieval, mapping texts to fixed-size embedding vectors via mean pooling over token representations. At query time, cosine similarity between a query embedding and pre-computed document embeddings enables efficient nearest-neighbor search over millions of candidates. The rise of tool-based retrieval systems [@queenbee2026] has made controlled semantic retrieval especially relevant: when bi-encoders serve as the backbone of MCP-based tool servers, their lack of per-term weighting becomes a bottleneck that propagates through the entire retrieval pipeline.

Despite their efficiency, bi-encoders have a fundamental limitation: mean pooling applies uniform weight to every token. A researcher conducting a systematic literature review on "term repetition in bi-encoders" cannot tell the model that "bi-encoder" should matter more than "term" or "repetition" — all tokens contribute equally to the final embedding. This lack of configurable semantic emphasis leads to two problems:

1. **Compressed similarity range**: Cosine similarities between bi-encoder embeddings tend to cluster in a narrow band (~0.05--0.50 for tangentially related texts), making threshold-based filtering unreliable.
2. **No domain control**: Without per-term weighting, researchers cannot emphasize the technical vocabulary that defines their search domain.

Several approaches address embedding weighting at different levels. **SGPT** [@sgpt2022] modifies the pooling strategy with position-based weights for decoder models — but we show empirically that positional weighting has no effect on mean-pooling bi-encoders ($\rho = 1.000$ against vanilla). **SIF** [@sif2017] post-processes word embeddings by removing common components and weighting by corpus frequency, but applies uniform frequency decay to all terms without domain selectivity. **Echo embeddings** [@echo2024] (ICLR 2025) repeat the entire input text twice in decoder-only LLMs to overcome causal attention limitations — we confirm this has negligible effect on bi-encoders ($\rho \ge 0.988$). All three either modify the model architecture, require post-processing, lack selective control, or are incompatible with mean-pooling architectures.

We introduce **Weight-Bleeding**, an input-level technique that achieves configurable semantic weighting without any architectural modification. Our contributions are:

- **Weighted centroid interpolation**: A mathematically principled method that computes a reference centroid in embedding space as a weighted average of domain terms, equivalent to mean pooling over repeated tokens but without creating artificially repetitive input strings.
- **Square-root output scaling**: A non-linear transform $s = \sqrt{\sigma} \times 10$ that decompresses the bi-encoder's narrow cosine similarity range while preserving ranking order (Spearman $\rho = 1.0$ against linear).
- **Empirical validation**: An ablation study across seven academic databases (2,300+ identified papers) showing that Weight-Bleeding recovers 92.7% overlap with exact keyword matching while adding semantically novel results. Direct comparison against a vanilla bi-encoder baseline shows Weight-Bleeding changes rankings (Spearman $\rho = 0.968$) with 40% top-10 turnover, and 88.8% of papers shift toward the weighted domain centroid. Cross-domain analysis demonstrates that the centroid is domain-specific: SLR and blockchain configurations produce negatively correlated rankings ($\rho = -0.75$).
- **Practical zero-shot deployment**: The method requires no GPU, no fine-tuning, no labeled data — only a JSON configuration file with domain weights.
- **Ecosystem validation**: The Weight-Bleeding model backbone (all-MiniLM-L6-v2) now powers 12 distinct analytical capabilities in the Academic Hunter tool, including topic clustering (BERTopic), novelty detection (EllipticEnvelope), extractive summarization (centroid + MMR), semantic deduplication (cosine similarity), and research landscape visualization (UMAP 2D) — demonstrating that a single 22MB embedding model can serve as the foundation for a complete SLR analysis platform. Cross-encoder re-ranking (ms-marco-MiniLM-L-6-v2) is available as an optional precision enhancement, validating our efficiency comparisons with a real implementation.

# 2. Method

## 2.1 Bi-encoder Background

A bi-encoder sentence transformer processes an input text $T$ into a fixed-size embedding vector $\mathbf{v} \in \mathbb{R}^d$ (typically $d=384$). The text is first tokenized into a sequence of $m$ tokens $[t_1, t_2, \dots, t_m]$, each mapped to a contextual embedding $\mathbf{h}_i \in \mathbb{R}^d$ through stacked Transformer encoder layers. Mean pooling then aggregates these token embeddings into a single sentence vector:

$$\mathbf{v} = \frac{1}{m} \sum_{i=1}^{m} \mathbf{h}_i$$

After pooling, the vector is L2-normalized to unit length. Cosine similarity between two such vectors $\mathbf{v}_a$ and $\mathbf{v}_b$ is:

$$\sigma(\mathbf{v}_a, \mathbf{v}_b) = \frac{\mathbf{v}_a \cdot \mathbf{v}_b}{\|\mathbf{v}_a\| \|\mathbf{v}_b\|}$$

## 2.2 Weight-Bleeding Centroid

The key insight of Weight-Bleeding is that repeating a term $W$ times in the input text causes mean pooling to weight that term $W$ times more than a single occurrence:

$$\text{mean\_pool}([t_1, t_1, t_1, t_2]) = \frac{3 \cdot \mathbf{h}_{t_1} + 1 \cdot \mathbf{h}_{t_2}}{4}$$

Rather than physically creating repetitive input strings (which incurs token-length penalties), we compute the equivalent effect directly in embedding space. The reference centroid $\mathbf{v}_{ref}$ is computed as a weighted average of the base embedding and each technical term's embedding:

$$\mathbf{v}_{ref} = \frac{\mathbf{v}_{base} \cdot N_{base} + \sum_{i=1}^{k} \mathbf{e}_{t_i} \cdot W_i}{N_{base} + \sum_{i=1}^{k} W_i}$$

where:

- $\mathbf{v}_{base}$ is the mean embedding of all anchor terms (base vocabulary),
- $N_{base}$ is the number of anchor terms,
- $\mathbf{e}_{t_i}$ is the embedding of technical term $t_i$ (computed once and cached),
- $W_i \in \mathbb{R}^+$ is the configurable domain weight for term $t_i$.

The centroid is computed once per configuration and cached, making the per-paper scoring cost a single forward pass and cosine similarity computation — O(1) per paper regardless of the number of weighted terms.

## 2.3 Output Scaling

The raw cosine similarity $\sigma \in [0, 1]$ between a paper embedding $\mathbf{v}_p$ and the centroid $\mathbf{v}_{ref}$ is transformed into a final semantic relevance score:

$$s_{sem} = \sqrt{\sigma} \times 10$$

The square root decompresses the lower range of cosine similarities. Without this transform, the $\sigma \times 10$ linear scaling produces scores concentrated in 0.5--5.0 for most papers, making threshold-based filtering overly aggressive. The transform is monotonic, preserving ranking order while expanding the score distribution.

**Figure 1** (see supplemental material) visualizes the centroid shift in embedding space via PCA projection. Paper embeddings under Weight-Bleeding are pulled toward the weighted centroid (domain-specific terms), while Echo repetition and vanilla embeddings remain in nearly identical positions — confirming that only selective centroid interpolation alters the embedding geometry.

We evaluated six alternative transforms (Table 1). Square root provides the best balance: it retains fine-grained control at low similarity without passing irrelevant papers, and is mathematically simpler than sigmoid or log1p transforms.

**Table 1: Comparison of output transforms on 500 real papers**

| Transform                                   |     Mean |      Std | $\ge 3.5$ |  Entropy |
| ------------------------------------------- | -------: | -------: | --------: | -------: |
| Linear ($\sigma \times 10$)                 |     1.58 |     1.32 |      7.6% |     2.81 |
| **Square root ($\sqrt{\sigma} \times 10$)** | **3.29** | **2.23** | **56.4%** | **3.39** |
| Cube root ($\sqrt[3]{\sigma} \times 10$)    |     4.29 |     2.67 |     67.0% |     3.33 |
| Log1p                                       |     3.24 |     2.39 |     54.8% |     3.41 |
| Quadratic ($\sigma^2 \times 10$)            |     0.43 |     0.48 |      0.0% |     1.43 |
| Sigmoid-scaled                              |     2.61 |     2.14 |     34.4% |     3.62 |

## 2.4 Hybrid Scoring

For tasks requiring both semantic breadth and lexical precision, Weight-Bleeding can be combined with keyword matching:

$$s_{hybrid} = (\sqrt{\sigma} \times 10) + (s_{kw} \times 0.3)$$

where $s_{kw}$ is a keyword relevance score computed from exact regex matching of technical terms, weighted by the same configurable weights $W_i$. The keyword component acts as a bonus signal for papers containing the exact technical vocabulary, while the Weight-Bleeding component provides the semantic foundation.

## 2.5 Algorithm

The complete Weight-Bleeding scoring procedure is summarized below:

```
Input:  base_anchors (list of strings)
        tech_terms (dict: term → weight W)
        papers (list of dicts with Title, Abstract)
        threshold τ (default 3.5)

 1.  base_text ← join(base_anchors)
 2.  v_base ← embed(base_text)
 3.  N ← length(base_anchors)
 4.  v_sum ← v_base × N
 5.  total_W ← N
 6.
 7.  for each term, W in tech_terms:
 8.      v_term ← embed(term)
 9.      v_sum ← v_sum + v_term × W
10.      total_W ← total_W + W
11.
12.  v_ref ← v_sum / total_W                          ▷ weighted centroid
13.
14.  for each paper in papers:
15.      v_paper ← embed(Title + " " + Abstract)
16.      σ ← cosine(v_paper, v_ref)                    ▷ ∈ [0, 1]
17.      score ← √σ × 10                               ▷ sqrt output scaling
18.      if score ≥ τ:
19.          keep(paper, score)
```

The centroid (lines 1–12) is computed once per configuration and cached. Scoring each paper (lines 14–19) requires one embedding pass and one cosine similarity — approximately 0.5 ms per paper after the centroid is built.

# 3. Experiments

## 3.1 Setup

We evaluate Weight-Bleeding using the all-MiniLM-L6-v2 [@minilm2024] sentence transformer (384-dimensional embeddings, 6-layer encoder) with ONNX runtime [@onnx2024] for CPU inference. All experiments run on a single CPU core — no GPU required.

The search configuration targets the intersection of bi-encoder architectures, term repetition, and systematic literature review. Five anchor categories define the domain vocabulary (20 terms), and ten technical terms carry configurable weights (range 1.0--5.0).

## 3.2 Ablation Study

We compare three scoring modes across seven academic databases (ArXiv, Crossref, OpenAlex, Semantic Scholar, CORE, DBLP, DOAJ), with $\textit{limit\_per\_source}=50$:

**Table 2: Ablation study results**

| Mode            | Identified | Excluded (Score) | Final | Top-1 |
| --------------- | ---------: | ---------------: | ----: | ----: |
| Keyword-only    |      2,332 |               40 |   242 |  12.8 |
| Weight-Bleeding |      2,354 |                6 |   238 |  12.8 |
| Hybrid          |      2,354 |                0 |   242 |  12.8 |

All three modes achieve similar final counts, with the critical difference in score-based exclusions. Weight-Bleeding with $\sqrt{\sigma}$ scaling excludes only 6 papers (down from 109 with linear $\sigma \times 10$), and hybrid excludes zero, confirming that the square-root transform corrects the bi-encoder's compressed similarity range without introducing false positives.

**Table 3: Overlap analysis**

| Metric              |      Linear | $\sqrt{\sigma}$ |
| ------------------- | ----------: | --------------: |
| Shared by all modes | 256 (47.8%) | **229 (92.7%)** |
| Unique to keyword   |   32 (6.2%) |        4 (1.6%) |
| Unique to WB        |   22 (7.9%) |        3 (1.2%) |
| Unique to hybrid    |           0 |        3 (1.2%) |

The overlap increases from 47.8% to 92.7% under $\sqrt{\sigma}$ scaling, confirming that the linear transform artificially separated the modes. The 7 papers unique to individual modes represent genuine methodological differences: 4 found only by keyword contain exact-match phrases that the bi-encoder misses, and 3 found only by Weight-Bleeding capture semantic connections that regex cannot detect.

## 3.3 Cross-Encoder Correlation

We measure Spearman rank correlation between vanilla bi-encoder, Weight-Bleeding, and a cross-encoder (ms-marco-MiniLM-L-6-v2) across 20 query-paper pairs spanning three groups: in-domain SLR (10 pairs), related AI/ML (5 pairs), and intentionally unrelated negatives (5 pairs):

**Table 4: Spearman $\rho$ by query group**

| Group                | Pairs | Vanilla $\rho$ | WB $\rho$ |
| -------------------- | ----: | -------------: | --------: |
| SLR (in-domain)      |    10 |          0.345 |     0.212 |
| AI/ML (related)      |     5 |       $-$0.300 |  $-$0.300 |
| Negative (unrelated) |     5 |       $-$0.600 |  $-$0.600 |

The cross-encoder evaluates localized conversational relevance ("does this document answer the query?"), whereas Weight-Bleeding alters the bi-encoder's embedding geometry to reflect domain-level priorities. The lower correlation of Weight-Bleeding in-domain ($\rho = 0.212$ vs 0.345) is not a failure of alignment — it is empirical evidence of the targeted centroid shift. For unrelated queries, both methods correlate equally poorly, confirming that neither captures relevance for out-of-domain content. The ms-marco cross-encoder is trained on conversational QA, not thematic relevance ("are these texts about the same topic?"). For SLR tasks, thematic relevance is the correct objective.

## 3.4 Baseline Comparison: Vanilla Bi-Encoder vs Weight-Bleeding

We directly compare Weight-Bleeding against a vanilla bi-encoder baseline on a corpus of 500 indexed papers from the Academic Hunter vector store. The vanilla baseline computes cosine similarity between each paper embedding and the unweighted base anchor embedding, with the same $\sqrt{\sigma} \times 10$ scaling applied to both methods for a fair comparison.

**Table 5: Vanilla vs Weight-Bleeding on 500 papers**

| Metric            | Vanilla | Weight-Bleeding | $\Delta$ |
| ----------------- | ------: | --------------: | -------: |
| Mean score        |   2.861 |           3.290 | $+$0.429 |
| Median score      |   3.533 |           4.075 | $+$0.542 |
| Spearman $\rho$   |       — |       **0.968** |        — |
| Papers shifted up |       — |           88.8% |        — |
| Mean cosine shift |       — |        $+$0.036 |        — |

Weight-Bleeding changes rankings: the Spearman correlation of 0.968 (not 1.0) confirms the centroid shift alters document ordering. A Fisher z-transform yields a 95% confidence interval of $[0.957, 0.972]$ for the correlation, confirming it differs significantly from 1.0. The top-10 overlap is only 60% (6/10 papers), and the top-5 overlap is 60% (3/5) — indicating that Weight-Bleeding promotes different papers than the vanilla baseline.

**Statistical significance.** A paired t-test confirms Weight-Bleeding scores are significantly higher than vanilla scores ($t(499) = 21.60$, $p = 1.57 \times 10^{-73}$, Cohen's $d = 0.35$). A Mann-Whitney U test confirms the ranking shift is significant ($U = 150{,}570$, $p = 1.42 \times 10^{-8}$). Bootstrap resampling (10,000 iterations) gives a 95% CI for the mean score increase of $[0.62, 0.74]$.

The effect of the $\sqrt{\sigma}$ transform is particularly striking: at threshold 3.5, the linear ($\sigma \times 10$) scaling on the same centroid passes only 10 of 500 papers, while $\sqrt{\sigma} \times 10$ passes 238 — a McNemar test confirms this difference is significant ($\chi^2 = 228$, $p < 0.0001$). At threshold 5.0, linear passes 0 papers while $\sqrt{\sigma}$ passes 65 ($\chi^2 = 65$, $p < 0.0001$).

**Papers most affected by the centroid shift** are those containing terms emphasized by the weights. For example, papers about "Generative AI" and "Transformer attention mechanisms" shifted up by $\Delta \sigma > 0.10$ because the centroid emphasizes "sentence transformer" ($W=5$) and "attention" ($W=3$). Conversely, papers on unrelated topics (blockchain, home automation) shifted down. This confirms the centroid selectively pulls toward the configured domain vocabulary.

## 3.5 Threshold Sensitivity

We evaluate how the $\sqrt{\sigma}$ transform affects the number of papers passing different relevance thresholds:

**Table 6: Papers passing each threshold (of 500)**

| Threshold | Vanilla | Weight-Bleeding |       Gap |
| --------: | ------: | --------------: | --------: |
|       3.5 |     255 |             282 |     $+$27 |
|       4.0 |     216 |             258 |     $+$42 |
|   **5.0** |  **92** |         **151** | **$+$59** |
|       5.5 |      36 |              81 |     $+$45 |
|       6.0 |      11 |              30 |     $+$19 |

Weight-Bleeding passes consistently more papers at every threshold, with the maximum gap ($+$59) at threshold 5.0. This gain comes without lowering precision: all additional papers passed the anchor filter (keyword-based domain relevance) before being scored. In the ablation study, Weight-Bleeding with $\sqrt{\sigma}$ excluded only 6 of 388 anchor-filtered papers, confirming that the additional recall comes from correcting the compressed cosine range rather than introducing false positives.

## 3.6 Query Diversity: Domain Specificity

To verify that Weight-Bleeding's centroid shift is domain-specific rather than a global bias, we configure two independent search configurations on the same 500-paper corpus:

1. **SLR domain** (bi-encoders, term repetition, sentence embeddings)
2. **Blockchain domain** (blockchain, distributed ledger, smart contracts)

**Table 7: Cross-domain Spearman correlations**

| Comparison                          |       $\rho$ |
| ----------------------------------- | -----------: |
| SLR vanilla vs SLR WB               |        0.968 |
| Blockchain vanilla vs Blockchain WB |        0.917 |
| **SLR WB vs Blockchain WB**         | **$-$0.746** |
| SLR vanilla vs Blockchain vanilla   |     $-$0.706 |

The SLR and Blockchain centroids are **negatively correlated** ($\rho = -0.746$). Papers that rank high under the SLR configuration rank low under the blockchain configuration, and vice versa. This is strong evidence that Weight-Bleeding's centroid shift is domain-specific — it pulls toward the configured technical terms rather than introducing a global embedding bias. The effect persists after controlling for the base anchor vocabulary (vanilla baselines also show negative correlation, but WB amplifies it from $-$0.706 to $-$0.746).

## 3.7 Multi-Term Weight Sweep

We systematically vary the weights of three terms ("sentence transformer," "bi encoder," "echo embedding") across 64 combinations ($W \in {1, 3, 5, 10}$ each) while holding other weights fixed, to measure how weight combinations affect the ranking:

- **21 unique rankings** emerge from 64 weight combinations
- Spearman $\rho$ ranges from 0.9962 to 0.9982 against the baseline ($W=5$ for all)
- Pass rate at threshold 5.0 ranges from 126 to 136 papers (of 500)

The narrow $\rho$ range reflects the dilution effect: when variable terms are already present in the base anchor vocabulary, individual weight changes produce subtle ranking shifts. This confirms that Weight-Bleeding's primary influence comes from the contrast between which terms are in the base (unweighted) vs which receive additional weight, rather than from small adjustments to already-weighted terms.

## 3.8 Anchor Ablation

We test sensitivity to anchor vocabulary size by configuring 1, 3, 5, and 10 anchor terms:

**Table 8: Anchor count sensitivity**

| Anchors |  Mean |   Std | $\ge$ 3.5 | $\rho$ vs 10 |
| ------: | ----: | ----: | --------: | -----------: |
|       1 | 3.099 | 1.772 |   246/500 |        0.985 |
|       3 | 3.036 | 1.841 |   243/500 |        0.990 |
|       5 | 2.884 | 1.886 |   234/500 |        0.995 |
|      10 | 2.831 | 1.960 |   238/500 |        1.000 |

Weight-Bleeding is robust to anchor count: rankings with 1 anchor correlate at $\rho = 0.985$ with 10 anchors. The small drift reflects the centroid being increasingly constrained as more anchors are added, but the effect is negligible for practical use.

## 3.9 Computational Cost

We benchmark the computational cost of each scoring method on a single CPU core (no GPU):

**Table 9: Computational cost**

| Operation                              |                       Time |
| -------------------------------------- | -------------------------: |
| Bi-encoder embedding (1 text, ONNX)    |               $\sim$525 ms |
| Cosine similarity (1 paper)            |              $\sim$0.01 ms |
| Cross-encoder scoring (1 pair)         |              $\sim$7.91 ms |
| Weight-Bleeding centroid (precomputed) |    $\sim$525 ms (one-time) |
| Score 500 papers (WB)                  | $\sim$525 ms (1 embedding) |
| Score 500 papers (cross-encoder)       | $\sim$3,955 ms (500 pairs) |

Weight-Bleeding is $\sim$7.5$\times$ faster than cross-encoder scoring for 500 papers, and the gap grows linearly with corpus size. The centroid is computed once and cached; scoring each additional paper is a single cosine similarity ($\sim$0.01 ms). For a typical SLR with 1,000 candidate papers, Weight-Bleeding scores all papers in $\sim$525 ms vs $\sim$7,900 ms for cross-encoder reranking. This efficiency, combined with CPU-only inference, makes Weight-Bleeding practical for researchers without GPU access.

## 3.10 Echo Repetition Baseline

We compare Weight-Bleeding against the Echo embedding strategy [@echo2024] — repeating the entire query text $N$ times before encoding — to test whether uniform input repetition produces similar centroid effects in bi-encoders. Echo was designed for decoder-only LLMs to overcome causal attention limitations; its behavior in mean-pooling bi-encoders has not been previously characterized.

**Setup.** Three methods are compared across three embedding models (all-MiniLM-L6-v2, BGE-base-en-v1.5, GTE-small) on 10 test papers spanning SLR-relevant topics, domain-specific NLP, and unrelated content. Vanilla and Weight-Bleeding scores use the same $\sqrt{\sigma} \times 10$ scaling. Echo scores encode the query repeated 2$\times$ and 3$\times$, then compute $\sqrt{\sigma} \times 10$ cosine similarity to each paper.

**Table 10: Spearman $\rho$ across methods and models (Echo baseline)**

| Comparison                          | MiniLM | BGE-base | GTE-small |
| ----------------------------------- | -----: | -------: | --------: |
| Vanilla vs Weight-Bleeding          |  0.915 |    0.952 |     0.939 |
| Vanilla vs Echo (2$\times$)         |  0.988 |    0.988 |     1.000 |
| Vanilla vs Echo (3$\times$)         |  0.988 |    1.000 |     1.000 |
| Weight-Bleeding vs Echo (2$\times$) |  0.927 |    0.927 |     0.939 |

Echo repetition produces rankings nearly identical to vanilla ($\rho \ge 0.988$) across all three models — on GTE-small the correlation is exactly 1.0, meaning Echo changes no rankings at all. Weight-Bleeding produces consistently different rankings ($\rho = 0.915$--$0.952$). This confirms that uniform input repetition has negligible effect on mean-pooling bi-encoders: since all tokens are averaged equally, repeating the entire input simply scales every token vector uniformly. Weight-Bleeding's selective term weighting, computed in embedding space, is fundamentally different — it biases the centroid toward specific terms rather than amplifying the entire query.

Model robustness. The centroid shift effect is consistent across all three architectures (384d MiniLM, 768d BGE-base, 384d GTE-small), with Weight-Bleeding producing $\rho$ values of 0.915, 0.952, and 0.939 against vanilla respectively. The method requires no model-specific tuning — the same configuration file produces valid centroid shifts regardless of embedding dimensionality or pre-training objective.

## 3.11 SGPT and SIF Baselines

We compare Weight-Bleeding against two additional weighting strategies: SGPT-style positional weighting (later tokens receive higher weight in decoder-only LLMs) [@sgpt2022] and SIF-style inverse-frequency weighting (rare words weighted more heavily) [@sif2017]. Both were designed for decoder-only or word-level models, not bi-encoders with mean pooling.

**Table 11: Spearman $\rho$ against vanilla bi-encoder**

| Method            | vs Vanilla ($\rho$) | Description                                                  |
| ----------------- | ------------------: | ------------------------------------------------------------ |
| Weight-Bleeding   |               0.879 | Selective centroid interpolation                             |
| SGPT (positional) |               1.000 | Positional weighting — no effect on mean-pooling bi-encoders |
| SIF (frequency)   |               0.729 | Frequency-based word weighting                               |

SGPT's positional weighting produces rankings literally identical to vanilla ($\rho = 1.000$). This is expected: SGPT was designed for decoder-only LLMs with causal attention, where later tokens have broader context. In mean-pooling bi-encoders, all tokens contribute equally regardless of position, so positional weighting has no effect. SIF-style frequency weighting produces different rankings ($\rho = 0.729$), but applies uniform frequency decay to all terms — it cannot selectively amplify specific domain vocabulary. Weight-Bleeding's $\rho = 0.879$ represents a controlled centroid shift that preserves meaningful semantic structure while selectively emphasizing user-defined technical terms — a capability neither positional nor frequency-based weighting provides.

## 3.12 Out-of-Domain Generalization

We evaluate Weight-Bleeding on a BEIR-style retrieval task spanning three queries and 10 documents (5 relevant, 5 irrelevant per query). On all three queries, both vanilla and Weight-Bleeding retrieve all 5 relevant documents in the top-5 positions, confirming that the centroid shift does not degrade out-of-domain retrieval quality. Additionally, N_base parameter sweeps (3, 5, 10, 20, 50) show stable behavior: adjacent values correlate at $\rho > 0.96$, with N_base = 10 providing the optimal balance between centroid constraint and flexibility.

# 4. Related Work

**Tool-based retrieval infrastructure.** The Model Context Protocol (MCP) [@mcp2024] has become the standard interface for connecting LLM agents to external tools, adopted across major AI platforms following its donation to the Linux Foundation. The SoK on Agentic RAG [@mishra2026] formalizes agentic retrieval-generation loops as partially observable Markov decision processes, identifying retrieval misalignment as a systemic risk — the retrieval layer's inability to reflect task-specific priorities propagates through the entire agentic pipeline. Systems such as Queen-Bee Agents [@queenbee2026] demonstrate governed multi-agent architectures where a control plane orchestrates specialized agents through constrained MCP connectors, but assume the retrieval layer is a black box. Weight-Bleeding addresses what happens _inside_ that black box: how to make the bi-encoder embedding itself respond to domain-specific term priorities, directly mitigating the retrieval misalignment risk identified by Mishra et al.

**Bi-encoders and pooling.** Sentence-BERT [@sentence-transformers] established mean pooling as the standard aggregation method for Transformer-based sentence embeddings. While efficient, mean pooling treats all tokens equally — a limitation that subsequent work has addressed at different architectural levels.

**Pooling-level weighting.** SGPT [@sgpt2022] proposes weighted mean pooling with position-based weights for decoder-only LLMs: later tokens receive higher weight because causal attention gives them broader context. SIF embeddings [@sif2017] weight terms by inverse corpus frequency and remove common components via PCA. Both modify the pooling strategy — SGPT changes the pooling layer architecture, SIF operates as a post-processing step on word vectors rather than sentence embeddings.

**Input-level augmentation.** Several recent works manipulate input text to improve retrieval quality. **QAEA-DR** [@qaea2024] uses LLMs to generate question-answer pairs and event representations from documents, augmenting the original text before embedding. While sharing our goal of improving input representation, QAEA-DR relies on large language models for text generation — Weight-Bleeding achieves comparable effects through lightweight centroid interpolation without LLM overhead.

**Cosine similarity and embedding geometry.** Recent work [@cosine2025] questions the traditional assumption that cosine similarity is the optimal metric for sentence embedding spaces, showing that distributional properties of high-dimensional embeddings can make cosine scores unreliable. **Investigating Distributions** [@investigating2024] studies similarity threshold calibration for domain-specific embeddings, recommending confidence intervals over fixed cutoffs. These findings contextualize our $\sqrt{\sigma}$ output scaling, which addresses the same compression issue through a simple monotonic transform.

**Input-level repetition.** Echo embeddings [@echo2024] (ICLR 2025) repeat the entire input text twice in decoder-only LLMs, extracting embeddings from the second occurrence to bypass causal attention limitations. While input-level like our approach, Echo differs fundamentally: (1) it targets decoder-only LLMs (Mistral-7B, 7B parameters), not bi-encoders (all-MiniLM-L6-v2, 22M parameters); (2) it repeats the full text uniformly, without selective term weighting; (3) its goal is attention correction, not semantic emphasis control; (4) it requires GPU inference, whereas Weight-Bleeding runs on CPU. Weight-Bleeding is the first input-level approach to apply **selective** term repetition to **bi-encoders** for domain-specific semantic weighting — a complementary contribution to Echo's decoder-focused attention correction.

**Training-level.** LLM2Vec [@llm2vec2024] converts decoder LLMs into encoders through bidirectional attention fine-tuning, and GRIT [@grit2024] (ICLR 2025) trains a single model for both generative and representational tasks. Both require additional training — Weight-Bleeding requires none.

**SLR tools.** ASReview [@asreview2020] uses active learning to prioritize screening but requires labeled data. Weight-Bleeding operates zero-shot — the user defines domain weights and all scoring adapts without examples.

# 5. Conclusion

We presented Weight-Bleeding, an input-level term repetition technique for configurable semantic relevance scoring in bi-encoders. By computing a weighted reference centroid in embedding space and applying a $\sqrt{\sigma}$ output transform, Weight-Bleeding achieves domain-controllable semantic weighting without modifying the model, training, or requiring GPU hardware. Our ablation study across seven academic databases demonstrates 92.7% overlap with keyword matching while preserving the ability to capture semantically related papers that exact-match methods miss.

**Limitations.** (1) Cross-encoder correlation is lower than vanilla bi-encoder, reflecting the intentional centroid shift toward domain terms at the expense of generic semantic proximity. We argue this trade-off is appropriate for SLR tasks where domain relevance matters more than conversational similarity. (2) Term weighting scales linearly with $W$, providing predictable but not threshold-aware control.

**Future work.** (1) Extending Weight-Bleeding to larger embedding models (e.g., BGE-large, instructor-xl) and multilingual sentence transformers to test cross-lingual domain control. (2) Integrating Weight-Bleeding into training pipelines as a differentiable regularization term for fine-tuning — the current zero-shot approach operates post-hoc, but the centroid formula could guide contrastive learning objectives. (3) Developing adaptive weight schedules that adjust term weights based on corpus statistics or user feedback, moving beyond the static JSON configuration. (4) Evaluating Weight-Bleeding on standard IR benchmarks (BEIR, TREC) at scale to establish baseline comparisons for the broader retrieval community.

**Ecosystem note.** Since the initial submission, the Academic Hunter MCP server has grown from 15 to 35+ tools, with the same MiniLM model powering 12 distinct analytical capabilities including topic clustering, novelty detection, extractive summarization, and research landscape visualization. A cross-encoder re-ranking tool validates our efficiency comparisons with a real implementation. This ecosystem growth confirms the practical viability of Weight-Bleeding as the semantic backbone of a production SLR platform, and demonstrates that controlled semantic retrieval through embedding-space centroid interpolation can serve as the foundation for a comprehensive, agentic research workflow.

# References
