"""The identity of a paper, as every artifact of a run spells it.

Two ends of one join depend on this: the full-text ingest writes a chunk's
``parent_id`` with ``doc_id_for``, and the MCP tool that names those chunks
looks them up with the same function. An id derived two ways would leave the
chunks unreachable rather than wrong, which is the quieter failure.
"""

from academic_hunter.core.nlp.scorer import doc_id_for


def test_doc_id_prefers_doi():
    assert doc_id_for("Some Title", "10.1234/ABC") == "doi:10.1234/abc"


def test_doc_id_falls_back_to_normalised_title():
    assert doc_id_for("Sentence-BERT: Embeddings!") == "title:sentencebertembeddings"


def test_doc_id_normalises_case_and_punctuation():
    """Two spellings of the same title must produce the same id."""
    assert doc_id_for("A  Study, of Things!") == doc_id_for("a study of things")


def test_doc_id_of_blank_is_empty_title():
    assert doc_id_for("") == "title:"
