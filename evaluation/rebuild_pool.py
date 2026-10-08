"""Rebuild a pool's document ids under the identity rules the code now applies.

A pool is keyed by ``doc_id_for(title, doi)``, and the id is the join between
three artifacts: the pool, the grading page built from it, and the run's score
distribution, which ``sweep_threshold`` indexes by the same function. When the
id rule changes — or when a run starts resolving a DOI the pool was written
before — every key moves, and a judgment left on an old key lands on no paper:
``calibrate_inclusion_threshold`` counts it as a miss, in silence.

The pool is **not** re-selected. The documents are the ones already in the file,
found in the run's own CSV by title and re-keyed. Re-drawing the sample would
change the population a human was asked to judge, which is a different and much
larger change than the one this script makes.

Usage::

    python evaluation/rebuild_pool.py evaluation/pool_candidates_blockchain_ai.json

Then rebuild the page from the result (``build_pool_grading_page.py``).
"""

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from academic_hunter.core.evaluation.qrels import doc_id_for
from academic_hunter.core.models.utils import doi_from_url


def title_key(value):
    return " ".join(str(value or "").split()).lower()


def load_rows(csv_path):
    with open(csv_path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    by_title = {}
    for row in rows:
        by_title.setdefault(title_key(row.get("Title")), row)
    return by_title


def resolved_doi(row):
    """The row's DOI, or the one its own URL implies.

    Mirrors ``ResolveDoiStep``: what is already there wins, and only an arXiv URL
    implies one at all. A landing page implies nothing, and an invented DOI would
    be worse than the empty column the pool already carries for it.
    """
    doi = str(row.get("DOI") or "").strip()
    return doi or doi_from_url(row.get("URL"))


def run_csv(pool_path, source_csv):
    """The run's CSV, whether the pool names it from the root or from itself.

    The pools in this repository store it relative to the project root, which
    resolves only when the script is run from there. A rebuild that silently
    failed to find its own run would abort on the first document, so the two
    readings that make sense are tried before giving up.
    """
    for candidate in (Path(source_csv), Path(pool_path).resolve().parent.parent / source_csv):
        if candidate.exists():
            return candidate
    raise SystemExit(
        f"{pool_path} names {source_csv}, which is not there. Re-keying needs the "
        "run's own CSV; nothing else records what the documents were."
    )


def rebuild(pool_path):
    pool = json.loads(Path(pool_path).read_text(encoding="utf-8"))
    documents = pool.get("documents")
    if not isinstance(documents, dict) or not documents:
        raise SystemExit(f"{pool_path} carries no documents.")

    source_csv = pool.get("source_csv")
    if not source_csv:
        raise SystemExit(
            f"{pool_path} does not name the run it came from, so its documents "
            "cannot be re-keyed against anything."
        )
    csv_path = run_csv(pool_path, source_csv)
    by_title = load_rows(csv_path)

    rebuilt = {}
    renamed = []
    for old_id, doc in documents.items():
        key = title_key(doc.get("title"))
        row = by_title.get(key)
        if row is None:
            raise SystemExit(
                f"{old_id} ({doc.get('title')!r}) is not in {csv_path}. Re-keying "
                "it would have to guess, and a guessed key is a lost judgment."
            )
        doi = resolved_doi(row)
        new_id = doc_id_for(row.get("Title"), doi)
        if new_id in rebuilt:
            raise SystemExit(
                f"{old_id} and {rebuilt[new_id].get('title')!r} both key to "
                f"{new_id}: two judgment targets collapsed into one."
            )
        if new_id != old_id:
            renamed.append((old_id, new_id))
        rebuilt[new_id] = {**doc, "doi": doi}

    pool["documents"] = rebuilt
    pool["regeneration"] = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": "doc_id_for(title, doi or doi_from_url(url))",
        "documents": len(rebuilt),
        "renamed": len(renamed),
        "renames": [{"from": a, "to": b} for a, b in renamed],
    }
    Path(pool_path).write_text(
        json.dumps(pool, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return len(rebuilt), renamed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pool", help="the pool JSON to re-key in place")
    args = parser.parse_args()

    total, renamed = rebuild(args.pool)
    print(f"{args.pool}: {total} documents, {len(renamed)} re-keyed")
    for old_id, new_id in renamed:
        print(f"  {old_id}\n    -> {new_id}")


if __name__ == "__main__":
    main()
