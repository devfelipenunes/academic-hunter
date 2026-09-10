# Academic Hunter — Experiment Scripts

Scripts de validação para o paper do Academic Hunter com Weight-Bleeding.

## Scripts

### `run_ablation.py`

Ablation study comparing 3 scoring modes on the same search configuration:

- **keyword**: regex-only scoring (`semantic_weight=0`)
- **embedding**: embedding-only scoring (`keyword_weight=0`)
- **hybrid**: 70% keyword + 30% embedding (default)

Usage: `python run_ablation.py [--quick]`

### `cross_encoder_val.py`

Compares ranking correlation (Spearman) between:

- Bi-encoder cosine similarity (vanilla)
- Bi-encoder + Weight-Bleeding (targeted term repetition)
- Bi-encoder + naive repetition (whole-query 3x)
- Cross-encoder relevance score (ms-marco-MiniLM-L-6-v2)

The cross-encoder measures search relevance ("does this answer the query?")
which differs from semantic similarity ("are these about the same topic?").
For SLR, semantic similarity is often more appropriate.

Usage: `python cross_encoder_val.py [--quick]`

### `weight_sensitivity.py`

Demonstrates that varying a term's weight in `technical_weights` changes
the embedding centroid and produces measurable ranking changes.

Usage: `python weight_sensitivity.py`

### `rerank_eval.py`

Measures the **second-stage cross-encoder** against the judged collection:
how many of the ranking's head documents it reorders, and what that buys.
Holds the first stage fixed at BM25 (the shipped query-mode signal) and sweeps
`top_n`, plus an oracle that reranks the whole pool as a ceiling.

It is the measurement behind `settings.rerank` in the pipeline. Measured
nDCG@10: `bm25` 0.6728 → `rerank@20` **0.7668** → oracle 0.7916, winning on both
topics. Note the contrast with the bi-encoder embedding, which _lowers_ nDCG
monotonically as its weight grows — the two are not interchangeable, and only
the judged collection separates them.

On the caution above: the cross-encoder measures relevance _to a query_, so it
is the wrong tool when there is no query — which is why the pipeline stage
requires `settings.ranking_query` and does nothing without one.

Usage: `python rerank_eval.py [--top-n 5,10,20,30] [--no-oracle]`

## Results

All outputs go to `results/`:

- `results/ablation_results.json`
- `results/cross_encoder_correlation.json`
- `results/weight_sensitivity.csv`
- `results/rerank_eval.json`
- `results/tables/` — LaTeX tables for the paper
