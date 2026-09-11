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

### `fulltext_eval.py`

Measures **full-text chunk retrieval** against the judged collection: does
retrieving 180-word passages rank _papers_ better than BM25 over title +
abstract? It fetches, chunks and indexes the judged documents through the same
ingest loop the pipeline step runs (`core.fulltext.ingest`), into its own
collection — `paper_chunks_eval`, in its own database — so experiment data can
never reach `chunk_search`.

**The candidate set is restricted to documents that have chunks**, and every
strategy, BM25 included, ranks that same set. This is not the pool-selection
mistake the evaluation README warns about: **25 of the 108 judged documents have
no DOI at all**, so no full-text system could ever fetch them, and scoring chunk
retrieval over the unrestricted pool would measure that ceiling rather than the
retriever. The ceiling is 65.5% of the genre pool and 90.0% of the blockchain
pool.

The hypothesis is declared in the docstring before the measurement: `chunk_level`
raises nDCG@10 above `paper_level` measured in the same run. Measured:

| strategy                       | nDCG@5 | nDCG@10 | nDCG@20 |    MRR |
| ------------------------------ | -----: | ------: | ------: | -----: |
| `paper_level (bm25)`           | 0.5091 |  0.4801 |  0.4616 | 0.8000 |
| `chunk_level (max, all)`       | 0.6346 |  0.5565 |  0.5329 | 0.9000 |
| `chunk_level (mean_top3)`      | 0.6790 |  0.5729 |  0.5489 | 1.0000 |
| `chunk_level@50 (max)`         | 0.6346 |  0.5565 |  0.5329 | 0.9000 |
| `hybrid (bm25 + chunk, 50/50)` | 0.5582 |  0.5240 |  0.5005 | 0.8000 |

**Read the basis before quoting the delta.** It is 5 of 11 queries over **one
topic**: all six genre-analysis queries were excluded, because only 3 of their 58
pool documents have chunks, which is below `--min-subset`. The per-topic table
prints `n/a` for genre for that reason, and the headline `+0.0764` nDCG@10 is
blockchain only. `mean_top3` beating `max` is worth a look rather than a
conclusion — with 16 candidates, the two reductions are ranking nearly the same
short list.

Coverage: **19 of 108** judged documents, 737 chunks. 19 obtained, 35 with no
open-access copy, 29 failed to download, 25 with no DOI. The failures are
recorded with their reason in `papers/evaluation/fulltext_coverage.json`, which
matters because `download_failed` covers three different situations — a
transient error, an open-access copy that is only a landing page, and a
publisher refusing a non-browser client — and only the first is worth retrying.
Retrying recovered one document between runs, which is exactly the distinction
the recorded reason is for.
On this corpus the Europe PMC leg retrieved nothing: the collection is applied
linguistics, which PMC does not index. The leg earns its place on biomedical
corpora, not this one, and the coverage report says which leg delivered each
document.

Usage: `python fulltext_eval.py --fetch` (first run, downloads), `--refresh`
(re-fetch and reindex everything), `--limit 5` (smoke test before spending
hundreds of downloads), `--min-subset 1` (compare even when the restricted set
is tiny).

## Results

All outputs go to `results/`:

- `results/ablation_results.json`
- `results/cross_encoder_correlation.json`
- `results/weight_sensitivity.csv`
- `results/rerank_eval.json`
- `results/fulltext_eval.json`
- `results/tables/` — LaTeX tables for the paper

`fulltext_eval.py` also writes `papers/evaluation/fulltext_coverage.json`, which
travels with the judged collection because it is what makes the chunk-retrieval
number readable without redoing the network.
