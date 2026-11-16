# Evaluation fixtures

Data that has to be in git for the retrieval measurement to run anywhere but on
the machine that made it. `results/` is not versioned — it is one run per search,
it is large, and it is yours — so a clone had no corpus to measure and
`tests/evaluation/harness.py` died on it.

## `run_20261013_093241/`

The run `qrels_blockchain.json` was written against: its own `run` field names
it. `make eval-run` points here by default, and the number it prints is the one
the committed qrels describes — 25 questions, all 25 targets resolved.

`academic_dataset_*.csv` is the file the run wrote, unedited. Three of its
columns are what the harness reads — `Title`, `Abstract`, `DOI` — and it
deliberately ignores the rest, including every recorded score: `_kw_score`,
`_hybrid_score` and the others are recomputed from the text by the shipped
`BM25`, `fuse_scores` and `rerank_texts`, so a change to any of them moves the
number. A live copy of the file's 28 columns is there for anyone who wants to
check that claim rather than take it.

Pointing `--run` at a run on another topic is allowed and resolves none of the
25 targets; the harness says so instead of printing a zero that looks like a
score.

## `pool_blockchain_governance.json`, one directory up

The other measurement, and the one that needs nothing from `results/`: five
queries over a fixed set of 50 candidates, graded 0–2, with its own provenance
block. It is what `make eval` runs. The corpus it was pooled from is gone and
never was in git, which the file records — so it measures how well a ranking
orders a candidate set, not what the candidate set was drawn from.
