# Microplastics known-item retrieval seed baseline

**Run date:** 2026-11-16  
**Corpus:** `research/microplastics-freshwater/consolidated-adjudication-round3.csv` (149 records)  
**Queries:** 10 bilingual known-item questions in `qrels_microplastics_known_item_seed.json`  
**Reranker:** off

| Retrieval mode | Recall@10 | nDCG@10 | MRR | Median rank |
|---|---:|---:|---:|---:|
| BM25 only (`weights=1,0`) | 0.9000 | 0.8631 | 0.8513 | 1 |
| Dense only (`weights=0,1`) | 1.0000 | 0.8518 | 0.8033 | 1 |
| Hybrid (`weights=0.7,0.3`) | 0.9000 | 0.8631 | 0.8591 | 1 |

These are smoke-test measurements, **not evidence that one ranking method is scientifically better**. Each question has one target article, and the target pairs were derived from a single AI-adjudicated review matrix; no human reviewer has validated them. This task measures known-item retrieval, not screening recall, scientific relevance across all candidates, or answer quality. Add independently human-judged relevant and non-relevant records before using these metrics to change production ranking.

The embedding leg uses ChromaDB's default ONNX MiniLM embedding function. The harness embeds the fixed corpus once per process and reuses those vectors across questions. The reranker was not included in this baseline.

## Provisional relevance-pool stress test

**Pool:** `microplastics_relevance_pool_seed.json` (5 queries, 12 candidates each, 44 unique records)
**Labels:** AI-proposed grades; human adjudication pending
**Reranker:** off

| Retrieval mode | nDCG@10 |
|---|---:|
| BM25 only (`weights=1,0`) | 0.8773 |
| Dense only (`weights=0,1`) | 0.8034 |
| Hybrid (`weights=0.7,0.3`) | 0.8774 |

The hybrid and BM25 scores are effectively tied on this small provisional pool. These numbers are a pipeline stress test only: the relevance grades were proposed by AI from titles, abstracts, and existing matrix decisions, and have not been independently reviewed. They should not drive a production ranking change. The candidate pool and human review worksheet are versioned beside the dataset; rerun after human adjudication before drawing scientific conclusions.
