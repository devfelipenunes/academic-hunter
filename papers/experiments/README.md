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

## Results

All outputs go to `results/`:

- `results/ablation_results.json`
- `results/cross_encoder_correlation.json`
- `results/weight_sensitivity.csv`
- `results/tables/` — LaTeX tables for the paper
