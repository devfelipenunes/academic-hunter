"""Re-keying a pool moves the keys and nothing else.

A pool's ids are the join between the pool, the grading page built from it and
the run's score distribution. When the id rule changes, every key moves at once
— and a judgment left on an old key lands on no paper, which
``calibrate_inclusion_threshold`` counts as a miss without saying so.

The rebuild is therefore allowed to change the ids and the ``doi`` field it
derives them from, and nothing else: not the documents, not the selection, not
the query. It is not allowed to guess — a document it cannot find in the run's
own CSV aborts the whole file rather than losing one judgment target quietly.
"""

import json

import pytest

from academic_hunter.core.evaluation.qrels import doc_id_for
from evaluation.rebuild_pool import rebuild

CSV_HEADER = "Title,DOI,URL\n"


def write_csv(tmp_path, rows):
    path = tmp_path / "run.csv"
    lines = [CSV_HEADER]
    for title, doi, url in rows:
        lines.append(f'"{title}","{doi}","{url}"\n')
    path.write_text("".join(lines), encoding="utf-8")
    return path


def document(title, doi="", **extra):
    return {"title": title, "doi": doi, "abstract": "A.", "year": "2024", **extra}


def write_pool(tmp_path, documents, csv_path, source_csv=None):
    path = tmp_path / "pool.json"
    path.write_text(
        json.dumps({
            "source_csv": str(source_csv if source_csv is not None else csv_path),
            "selection": "top-25 UNION random-25",
            "ranking_query": "How does AI meet ledgers?",
            "documents": documents,
        }),
        encoding="utf-8",
    )
    return path


PREPRINT_TITLE = "Smart contract auditing with a language model"


def test_a_title_keyed_preprint_is_re_keyed_to_its_arxiv_doi(tmp_path):
    """O conector do arXiv não publica DOI, e o URL nomeia o trabalho.

    Medido no pool de blockchain × IA: 16 dos 50 documentos estavam neste estado.
    """
    csv_path = write_csv(
        tmp_path, [(PREPRINT_TITLE, "", "http://arxiv.org/abs/2401.00001v2")]
    )
    old_id = doc_id_for(PREPRINT_TITLE, "")
    path = write_pool(tmp_path, {old_id: document(PREPRINT_TITLE)}, csv_path)

    total, renamed = rebuild(str(path))

    payload = json.loads(path.read_text(encoding="utf-8"))
    new_id = doc_id_for(PREPRINT_TITLE, "10.48550/arxiv.2401.00001")

    assert total == 1 and len(renamed) == 1
    assert set(payload["documents"]) == {new_id}
    assert payload["documents"][new_id]["doi"] == "10.48550/arxiv.2401.00001"


def test_a_document_that_already_has_a_doi_is_not_touched(tmp_path):
    doi = "10.1145/3576915.3623202"
    csv_path = write_csv(tmp_path, [("Published work", doi, "https://doi.org/" + doi)])
    path = write_pool(
        tmp_path, {doc_id_for("Published work", doi): document("Published work", doi)}, csv_path
    )

    total, renamed = rebuild(str(path))

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert total == 1 and renamed == []
    assert set(payload["documents"]) == {doc_id_for("Published work", doi)}


def test_a_landing_page_still_implies_no_doi(tmp_path):
    """Um DOI inventado a partir de uma landing page é pior do que a coluna vazia."""
    csv_path = write_csv(
        tmp_path, [("A work behind a landing page", "", "https://core.ac.uk/works/1")]
    )
    old_id = doc_id_for("A work behind a landing page", "")
    path = write_pool(tmp_path, {old_id: document("A work behind a landing page")}, csv_path)

    _, renamed = rebuild(str(path))

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert renamed == []
    assert payload["documents"][old_id]["doi"] == ""


def test_the_documents_and_the_query_are_carried_over_unchanged(tmp_path):
    """O rebuild move chaves; não re-sorteia a população que alguém vai julgar."""
    csv_path = write_csv(
        tmp_path,
        [(PREPRINT_TITLE, "", "http://arxiv.org/abs/2401.00001v2"), ("Kept", "10.1/kept", "u")],
    )
    documents = {
        doc_id_for(PREPRINT_TITLE, ""): document(PREPRINT_TITLE, abstract="Long text."),
        doc_id_for("Kept", "10.1/kept"): document("Kept", "10.1/kept"),
    }
    path = write_pool(tmp_path, documents, csv_path)
    before = json.loads(path.read_text(encoding="utf-8"))

    rebuild(str(path))

    after = json.loads(path.read_text(encoding="utf-8"))
    assert sorted(d["title"] for d in after["documents"].values()) == sorted(
        d["title"] for d in before["documents"].values()
    )
    assert after["ranking_query"] == before["ranking_query"]
    assert after["selection"] == before["selection"]
    assert after["source_csv"] == before["source_csv"]
    assert sorted(d["abstract"] for d in after["documents"].values()) == sorted(
        d["abstract"] for d in before["documents"].values()
    )


def test_the_regeneration_is_recorded_in_the_file(tmp_path):
    """Quem lê o pool depois tem de poder ver que as chaves mudaram, e porquê."""
    csv_path = write_csv(
        tmp_path, [(PREPRINT_TITLE, "", "http://arxiv.org/abs/2401.00001v2")]
    )
    path = write_pool(
        tmp_path, {doc_id_for(PREPRINT_TITLE, ""): document(PREPRINT_TITLE)}, csv_path
    )

    rebuild(str(path))

    record = json.loads(path.read_text(encoding="utf-8"))["regeneration"]
    assert record["documents"] == 1
    assert record["renamed"] == 1
    assert record["renames"][0]["to"] == doc_id_for(PREPRINT_TITLE, "10.48550/arxiv.2401.00001")


def test_a_document_the_run_does_not_contain_aborts_the_whole_file(tmp_path):
    """Adivinhar a chave de um documento é perder o julgamento que estava nela."""
    csv_path = write_csv(tmp_path, [("Something else", "10.1/other", "u")])
    old_id = doc_id_for("A document from another run", "")
    path = write_pool(tmp_path, {old_id: document("A document from another run")}, csv_path)
    before = path.read_text(encoding="utf-8")

    with pytest.raises(SystemExit) as raised:
        rebuild(str(path))

    assert "A document from another run" in str(raised.value)
    assert path.read_text(encoding="utf-8") == before, "o arquivo foi escrito apesar do aborto"


def test_two_documents_that_would_collapse_into_one_key_abort(tmp_path):
    """Duas entradas com o mesmo título e o mesmo DOI são um alvo só, não dois."""
    csv_path = write_csv(
        tmp_path,
        [(PREPRINT_TITLE, "", "http://arxiv.org/abs/2401.00001v2"),
         (PREPRINT_TITLE, "", "http://arxiv.org/abs/2401.00001v1")],
    )
    path = write_pool(
        tmp_path,
        {
            doc_id_for(PREPRINT_TITLE, "10.48550/arxiv.2401.00001"): document(PREPRINT_TITLE),
            doc_id_for(PREPRINT_TITLE, ""): document(PREPRINT_TITLE),
        },
        csv_path,
    )

    with pytest.raises(SystemExit) as raised:
        rebuild(str(path))

    assert "collapsed" in str(raised.value)


def test_a_pool_that_names_no_run_aborts(tmp_path):
    """Sem o CSV de origem não há contra o que re-derivar um id."""
    path = tmp_path / "pool.json"
    path.write_text(json.dumps({"documents": {"title:x": document("X")}}), encoding="utf-8")

    with pytest.raises(SystemExit) as raised:
        rebuild(str(path))

    assert "does not name the run" in str(raised.value)
