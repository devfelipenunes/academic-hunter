#!/usr/bin/env python3
"""Measure full-text chunk retrieval against the judged collection.

Every retrieval claim this project has made was over title + abstract. This asks
whether retrieving 180-word passages ranks *papers* better.

The hypothesis, declared before the measurement: ``chunk_level`` (best passage
per paper) raises nDCG@10 above ``paper_level`` (BM25 over title + abstract)
measured in the same run over the same candidate set. A null result would be a
finding about representation, not a bug — an abstract is a curated summary of
exactly what a topical query asks for, while a slice of the method section is a
worse match for one. The gain from chunks should be on specific needs ("which
dataset", "how many annotators"), which this qrels does not contain; that is a
limitation of the collection for this question, recorded rather than worked
around. If ``chunk_level`` loses badly everywhere, the first thing to test is
two-column reading order in ``pypdf``, and the fix is the adapter.

The candidate set is the judged documents of each query's pool that have chunks,
and every strategy — BM25 included — ranks that same set. 25 of the 108 judged
documents have no DOI at all, so no full-text system could fetch them; scoring
chunk retrieval over the unrestricted pool would measure that ceiling instead of
the retriever. Coverage is printed next to every number.

Calls the shipped code: the ingest loop is ``core.fulltext.ingest``, the fusion
is ``core.nlp.fusion.fuse_scores``, the metrics are ``core.evaluation``.

Usage:
    python papers/experiments/fulltext_eval.py                 # reuse what is indexed
    python papers/experiments/fulltext_eval.py --fetch         # download what is missing
    python papers/experiments/fulltext_eval.py --refresh       # re-fetch and reindex
"""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from retrieval_eval import load_documents

from academic_hunter.core.evaluation import (
    Timing,
    doc_id_for,
    documents_for,
    evaluate_run,
    load_qrels,
    mean_metrics,
    topics,
)
from academic_hunter.core.fulltext.ingest import STATUSES, ingest_full_text
from academic_hunter.core.infra import HunterConfig
from academic_hunter.core.nlp import BM25, fuse_scores
from academic_hunter.plugins.fulltext.compose import build_full_text_fetcher
from academic_hunter.plugins.vector_stores.chroma import ChromaVectorStore

RESULTS_DIR = Path(__file__).parent / "results"
EVAL_DIR = ROOT / "papers" / "evaluation"
DEFAULT_QRELS = EVAL_DIR / "qrels_pilot_genre_analysis.json"
COVERAGE_PATH = EVAL_DIR / "fulltext_coverage.json"

#: Its own database, not just its own collection: the evaluation must not be
#: able to change what `chunk_search` sees.
EVAL_DB = ROOT / ".academic_hunter" / "fulltext_eval_db"
EVAL_COLLECTION = "paper_chunks_eval"
PDF_CACHE = ROOT / ".academic_hunter" / "fulltext_eval"

KS = (5, 10, 20)
PAPER_LEVEL = "paper_level (bm25)"
CHUNK_ALL = "chunk_level (max, all)"
CHUNK_TOP_K = "chunk_level@{k} (max)"
CHUNK_MEAN = "chunk_level (mean_top3)"
HYBRID = "hybrid (bm25 + chunk, 50/50)"


def rank_by(ids, scores):
    """Ids best-first, ties broken by id: the total order the pipeline uses."""
    return [i for _, i in sorted(zip(scores, ids), key=lambda pair: (-pair[0], pair[1]))]


def collection_index(store, collection_name):
    """Per-paper chunk count and provenance, read from the collection.

    The port has no "count by parent" — it has `has_chunks`, which is a boolean,
    and asking it per document would be one round trip each. The provenance comes
    from here rather than from the papers dicts so that it survives a run that
    skipped already-indexed documents: the collection is the durable record.
    """
    try:
        collection = store.client.get_collection(collection_name)
    except Exception:
        # On a first run nothing is indexed yet; that is not a failure.
        return {}
    found = collection.get(include=["metadatas"])
    index: dict = {}
    for metadata in found.get("metadatas") or []:
        parent = metadata.get("parent_id", "")
        if not parent:
            continue
        entry = index.setdefault(parent, {"chunks": 0, "sources": Counter()})
        entry["chunks"] += 1
        if metadata.get("source"):
            entry["sources"][metadata["source"]] += 1
    return index


def best_by_parent(hits):
    """Best passage score per paper — the retrieval-aggregation rule."""
    best = {}
    for hit in hits:
        parent = hit.get("parent_id") or ""
        score = float(hit.get("relevance") or 0.0)
        if parent and score > best.get(parent, float("-inf")):
            best[parent] = score
    return best


def mean_top_k_by_parent(hits, k=3):
    """Mean of a paper's k best passages.

    Reported next to the max rather than instead of it: the mean punishes a long
    paper for having many mediocre passages, while the sum rewards length alone.
    If the two rankings disagree, that disagreement is the finding.
    """
    grouped = {}
    for hit in hits:
        parent = hit.get("parent_id") or ""
        if parent:
            grouped.setdefault(parent, []).append(float(hit.get("relevance") or 0.0))
    return {
        parent: sum(sorted(scores, reverse=True)[:k]) / min(k, len(scores))
        for parent, scores in grouped.items()
    }


def build_papers(documents):
    """The judged documents in the shape the ingest expects.

    Fails loudly if an id cannot be re-derived from its own document: the
    chunk→paper projection is an identity map over these ids, and a mismatch
    would silently score nothing.
    """
    papers = []
    for doc_id, doc in documents.items():
        title = str(doc.get("Title") or "")
        doi = str(doc.get("DOI") or "")
        derived = doc_id_for(title, doi)
        if derived != doc_id and doi:
            raise SystemExit(
                f"id mismatch for {doc_id!r}: doc_id_for gives {derived!r}. The "
                "chunk→paper projection assumes a map identity."
            )
        papers.append({"Title": title, "DOI": doi, "Year": doc.get("Year")})
    return papers


def fetch_full_text(papers, store, *, force, limit, time_budget):
    """Run the shipped ingest loop against the evaluation's own collection."""
    cfg = HunterConfig().fulltext_config()
    fetcher = build_full_text_fetcher(cfg["email"], PDF_CACHE)
    config = {
        **cfg,
        "max_papers": limit or len(papers),
        "time_budget_seconds": time_budget,
    }
    return ingest_full_text(
        papers, fetcher, store, config, force=force, collection_name=EVAL_COLLECTION
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qrels", default=str(DEFAULT_QRELS), help="judged collection")
    parser.add_argument("--fetch", action="store_true", help="download what is missing")
    parser.add_argument("--refresh", action="store_true", help="re-fetch and reindex")
    parser.add_argument("--limit", type=int, default=0, help="cap documents to fetch")
    parser.add_argument("--time-budget", type=int, default=1800, help="seconds for fetching")
    parser.add_argument("--chunk-top-k", type=int, default=50, help="head size for the @K row")
    parser.add_argument(
        "--min-subset",
        type=int,
        default=5,
        help="smallest restricted candidate set a query may have to be compared",
    )
    args = parser.parse_args()

    qrels_path = Path(args.qrels)
    qrels = load_qrels(qrels_path)
    documents, _ = load_documents(qrels_path)
    papers = build_papers(documents)

    store = ChromaVectorStore(db_dir=str(EVAL_DB))

    print("=" * 78)
    print("  Full-text chunk retrieval evaluation")
    print("=" * 78)
    print(f"  qrels      : {qrels_path.relative_to(ROOT)}")
    print(f"  documents  : {len(documents)} judged")
    print(f"  collection : {EVAL_COLLECTION} in {EVAL_DB.relative_to(ROOT)}")
    print()

    counters = None
    if args.fetch or args.refresh:
        print("  fetching full text (the shipped ingest loop)...")
        started = time.perf_counter()
        counters = fetch_full_text(
            papers,
            store,
            force=args.refresh,
            limit=args.limit,
            time_budget=args.time_budget,
        )
        elapsed = time.perf_counter() - started
        for status in STATUSES:
            if counters.get(status):
                print(f"    {status:<16} {counters[status]}")
        print(f"  ({elapsed:.0f} s)\n")

    fetched = bool(args.fetch or args.refresh)
    index = collection_index(store, EVAL_COLLECTION)
    indexed = {doc_id for doc_id in documents if index.get(doc_id)}
    total_chunks = sum(entry["chunks"] for entry in index.values())
    print(f"  indexed    : {len(indexed)}/{len(documents)} documents, "
          f"{total_chunks} chunks\n")

    # Only a run that fetched writes the coverage artefact; rewriting it from a
    # run that did not would replace every failure with "not attempted".
    if fetched:
        write_coverage(qrels, documents, papers, counters, index, indexed)
    else:
        print(f"  coverage   : reusing {COVERAGE_PATH.relative_to(ROOT)} "
              "(pass --fetch to refresh it)\n")

    if not indexed:
        print("  Nothing is indexed. Run with --fetch to download full text.")
        print("  The coverage artefact records why, when a fetch has been run.")
        return 2

    strategies, coverage_rows, excluded = {}, {}, []
    timing_bm25, timing_chunk = Timing(), Timing()

    for query_id, judgment in qrels.queries.items():
        pool = list(documents_for(qrels, query_id))
        subset = [doc_id for doc_id in pool if doc_id in indexed]
        if len(subset) < args.min_subset:
            excluded.append((query_id, len(pool), len(subset)))
            continue

        coverage_rows[query_id] = {
            "pool": len(pool),
            "with_chunks": len(subset),
            "coverage": round(len(subset) / len(pool), 4),
        }

        # BM25's corpus is the restricted set too: IDF is a property of the
        # candidate set, so a different one would be a different question.
        corpus = [f"{documents[d].get('Title', '')} {documents[d].get('Abstract', '')}"
                  for d in subset]

        started = time.perf_counter()
        bm25_scores = list(BM25(corpus).score(judgment.text))
        timing_bm25.per_query[query_id] = time.perf_counter() - started
        timing_bm25.pool_size[query_id] = len(subset)

        strategies.setdefault(PAPER_LEVEL, {})[query_id] = rank_by(subset, bm25_scores)

        started = time.perf_counter()
        all_hits = store.query_chunks(
            judgment.text, top_k=total_chunks, collection_name=EVAL_COLLECTION
        )
        head_hits = store.query_chunks(
            judgment.text, top_k=args.chunk_top_k, collection_name=EVAL_COLLECTION
        )
        timing_chunk.per_query[query_id] = time.perf_counter() - started
        timing_chunk.pool_size[query_id] = len(all_hits)

        by_max = best_by_parent(all_hits)
        by_mean = mean_top_k_by_parent(all_hits)
        max_scores = [by_max.get(d, 0.0) for d in subset]
        strategies.setdefault(CHUNK_ALL, {})[query_id] = rank_by(subset, max_scores)
        strategies.setdefault(CHUNK_MEAN, {})[query_id] = rank_by(
            subset, [by_mean.get(d, 0.0) for d in subset]
        )

        by_head = best_by_parent(head_hits)
        strategies.setdefault(CHUNK_TOP_K.format(k=args.chunk_top_k), {})[query_id] = rank_by(
            subset, [by_head.get(d, 0.0) for d in subset]
        )

        # 50/50, fixed before seeing the metric: choosing the weight afterwards
        # is choosing by the metric under test.
        fused = fuse_scores(
            bm25_scores,
            max_scores,
            strategy="weighted_norm",
            weights={"keyword": 0.5, "embedding": 0.5},
        )
        strategies.setdefault(HYBRID, {})[query_id] = rank_by(subset, list(fused))

    if not coverage_rows:
        print("  No query has enough chunk-backed documents to compare.")
        print("  That is the finding, not a crash — see papers/evaluation/README.md.")
        return 2

    reports = {}
    print("-" * 78)
    print(f"  {'strategy':<32} {'nDCG@5':>8} {'nDCG@10':>8} {'nDCG@20':>8} {'MRR':>8}")
    print("-" * 78)
    for name, rankings in strategies.items():
        report = evaluate_run(qrels, rankings, ks=KS)
        reports[name] = report
        mean = report.mean
        print(
            f"  {name:<32} {mean['ndcg@5']:>8.4f} {mean['ndcg@10']:>8.4f} "
            f"{mean['ndcg@20']:>8.4f} {mean['mrr']:>8.4f}"
        )
    print("-" * 78)

    baseline = CHUNK_ALL
    delta = reports[baseline].mean["ndcg@10"] - reports[PAPER_LEVEL].mean["ndcg@10"]
    # The basis goes with the verdict: this line is the one that gets quoted.
    print(f"\n  {baseline} vs {PAPER_LEVEL}: {delta:+.4f} nDCG@10"
          f"  ({'hypothesis holds' if delta > 0 else 'null — see the docstring'})")
    print(f"    over {len(coverage_rows)}/{len(qrels.queries)} queries, "
          f"{sorted({r['with_chunks'] for r in coverage_rows.values()})} candidate documents each")

    print(f"\n  queries compared: {len(coverage_rows)}/{len(qrels.queries)}"
          f"  (restricted candidate sets: "
          f"{min(r['with_chunks'] for r in coverage_rows.values())}–"
          f"{max(r['with_chunks'] for r in coverage_rows.values())} documents)")
    for query_id, pool_size, subset_size in excluded:
        print(f"    excluded {query_id}: {subset_size}/{pool_size} with chunks")
    for query_id, row in coverage_rows.items():
        print(f"    {query_id:<32} coverage {row['coverage']:.2%} "
              f"({row['with_chunks']}/{row['pool']})")

    # A mean over two unrelated corpora hides which one was helped.
    print("\n  nDCG@10 by topic")
    by_topic = {}
    for topic, query_ids in topics(qrels).items():
        row = {}
        for name, report in reports.items():
            subset_metrics = [report.per_query[q] for q in query_ids if q in report.per_query]
            row[name] = mean_metrics(subset_metrics).get("ndcg@10") if subset_metrics else None
        by_topic[topic] = row
        print(f"\n    {topic}")
        for name, value in row.items():
            shown = f"{value:.4f}" if value is not None else "n/a"
            marker = ""
            if value is not None and row.get(PAPER_LEVEL) is not None and name != PAPER_LEVEL:
                marker = f"  ({value - row[PAPER_LEVEL]:+.4f})"
            print(f"      {name:<32} {shown}{marker}")

    print(f"\n  cost: bm25 {timing_bm25.seconds_per_document * 1000:.2f} ms/document · "
          f"chunk retrieval {timing_chunk.seconds_per_document * 1000:.2f} ms/chunk")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "qrels": str(qrels_path.relative_to(ROOT)),
        "collection": EVAL_COLLECTION,
        "document_count": len(documents),
        "indexed_documents": len(indexed),
        "chunks": total_chunks,
        "ks": list(KS),
        "calls": (
            "core.fulltext.ingest.ingest_full_text (the pipeline step's loop), "
            "core.nlp.fusion.fuse_scores, core.evaluation"
        ),
        "strategies": {name: report.as_dict() for name, report in reports.items()},
        "by_topic": by_topic,
        "coverage": {
            "compared_queries": len(coverage_rows),
            "excluded_queries": {
                query_id: {"pool": pool, "with_chunks": subset}
                for query_id, pool, subset in excluded
            },
            "per_query": coverage_rows,
            "min_subset_required": args.min_subset,
        },
        "timing": {
            "bm25": timing_bm25.as_dict(),
            "chunk_retrieval": timing_chunk.as_dict(),
        },
        "notes": {
            "candidate_set": (
                "every strategy ranks the judged pool documents of that query "
                "that have chunks — restricted because 25 of the 108 judged "
                "documents have no DOI and no full-text system could fetch them"
            ),
            "aggregation": (
                "max over a paper's passages is the headline; mean_top3 is the "
                "robustness row"
            ),
            "fusion": "weighted_norm at 50/50, fixed before the measurement; never RRF",
            "page_numbers": (
                "none: the chunker works on character offsets, and the Europe PMC "
                "JATS source has no pages at all"
            ),
        },
    }
    out_path = RESULTS_DIR / "fulltext_eval.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  artefact: {out_path.relative_to(ROOT)}")
    print(f"  coverage: {COVERAGE_PATH.relative_to(ROOT)}")
    return 0


def write_coverage(qrels, documents, papers, counters, index, indexed):
    """Commit the coverage beside the judgments, so the number is readable offline.

    The status is the one the ingest wrote and the chunk counts are the
    collection's, never recomputed here: a second implementation of the tally
    would be free to disagree with the code that produced the data.

    What this does translate is the point of view. The artefact describes the
    *corpus* — which documents' full text the index holds — while
    ``_full_text_status`` describes a *run*, where a document whose chunks were
    already indexed is ``already_indexed`` rather than ``obtained``. Reporting
    the run's vocabulary here would make the same corpus read differently
    depending on whether it was the first fetch or the fifth.
    """
    by_id = {doc_id_for(str(p.get("Title") or ""), str(p.get("DOI") or "")): p
             for p in papers}

    per_document = {}
    for doc_id, doc in documents.items():
        entry = index.get(doc_id) or {}
        chunks = entry.get("chunks", 0)
        paper = by_id.get(doc_id) or {}
        status = paper.get("_full_text_status")
        if status == "already_indexed" and chunks:
            status = "obtained"
        if not status:
            status = "obtained" if chunks else "not_attempted"
        sources = entry.get("sources") or Counter()
        per_document[doc_id] = {
            "title": doc.get("title", ""),
            "doi": str(doc.get("DOI") or ""),
            "status": status,
            "source": paper.get("_full_text_source") or (sources.most_common(1)[0][0] if sources else ""),
            "chunks": chunks,
            # `download_failed` covers three causes; only one is worth retrying.
            "error": paper.get("_full_text_error", ""),
        }

    per_topic = {}
    for topic, query_ids in topics(qrels).items():
        pool = {d for qid in query_ids for d in documents_for(qrels, qid)}
        per_topic[topic] = {
            "pool": len(pool),
            "with_doi": sum(1 for d in pool if str(documents[d].get("DOI") or "").strip()),
            "with_chunks": sum(1 for d in pool if d in indexed),
        }

    payload = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "qrels": "papers/evaluation/qrels_pilot_genre_analysis.json",
        "collection": EVAL_COLLECTION,
        "chain": ["UnpaywallPdfSource", "EuropePmcSource"],
        "documents": len(documents),
        "with_doi": sum(1 for d in documents.values() if str(d.get("DOI") or "").strip()),
        # Tally of the per-document rows, so the two can never disagree.
        "counters": dict(Counter(row["status"] for row in per_document.values())),
        # What the fetching run itself did, which is a different question.
        "last_run_counters": counters or {},
        "chunks_total": sum(entry["chunks"] for entry in index.values()),
        "documents_with_chunks": len(indexed),
        "per_topic": per_topic,
        "per_document": per_document,
        "note": (
            "`status` describes the corpus, not the last run: a document whose "
            "full text the index already held is `obtained` here even though the "
            "run that regenerated this file skipped it. A document without a DOI "
            "is not a failure of the ingest — it is the structural ceiling of "
            "full-text coverage, and it is 23% of this collection."
        ),
    }
    COVERAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    COVERAGE_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


if __name__ == "__main__":
    sys.exit(main())
