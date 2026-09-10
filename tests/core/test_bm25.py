"""Tests for BM25.

The scoring formula has a few variants that differ in ways that matter — most
importantly the IDF, whose plain form goes negative for a term present in every
document and would turn a match into a penalty.
"""

import math

import pytest

from academic_hunter.core.nlp import BM25, bm25_scores, tokenize

DOCS = [
    "Hyperledger Fabric permissioned blockchain performance evaluation",
    "self-sovereign identity decentralised digital identity management",
    "e-government transparency accountability public administration",
    "IPFS off-chain storage integrated with blockchain systems",
]


# ── tokenizer ───────────────────────────────────────────────────────────────


def test_tokenize_lowercases_and_splits_on_punctuation():
    assert tokenize("Self-Sovereign Identity: A Survey!") == [
        "self", "sovereign", "identity", "a", "survey",
    ]


def test_tokenize_keeps_digits():
    """Years and model numbers carry signal in this corpus."""
    assert "2024" in tokenize("Published 2024, MiniLM-L6-v2")


def test_tokenize_of_empty_text():
    assert tokenize("") == []


# ── ranking behaviour ───────────────────────────────────────────────────────


def test_retrieves_the_document_containing_the_query_terms():
    index = BM25(DOCS)

    scores = index.score("self-sovereign identity")

    assert max(range(len(scores)), key=lambda i: scores[i]) == 1


def test_scores_are_aligned_with_the_input_order():
    index = BM25(DOCS)

    scores = index.score("IPFS storage")

    assert len(scores) == len(DOCS)
    assert scores[3] == max(scores)


def test_a_document_without_any_query_term_scores_zero():
    index = BM25(DOCS)

    scores = index.score("astrophysics")

    assert scores == [0.0] * len(DOCS)


def test_rarer_terms_outweigh_common_ones():
    """IDF is the point of BM25: 'blockchain' is in half the corpus, 'ipfs' in one."""
    index = BM25(DOCS)

    assert index.idf("ipfs") > index.idf("blockchain")


def test_idf_is_never_negative_for_a_universal_term():
    """The plain IDF form goes negative here, which would penalise a match.

    A term in every document still matches; it just cannot discriminate. The
    ``ln(1 + ...)`` variant keeps it at a small positive value instead.
    """
    index = BM25(["alpha beta", "alpha gamma", "alpha delta"])

    assert index.idf("alpha") > 0.0


def test_idf_of_an_absent_term_is_zero_not_an_error():
    """An unseen query term must not shift the scale of the others."""
    index = BM25(DOCS)

    assert index.idf("nonexistentterm") == 0.0


def test_repeating_a_query_term_does_not_change_the_ranking():
    """BM25 is bag-of-words; inflating a term is the weights' job, done openly."""
    index = BM25(DOCS)

    once = index.score("blockchain performance")
    thrice = index.score("blockchain blockchain blockchain performance")

    assert once == pytest.approx(thrice)


def test_longer_documents_are_penalised_by_length_normalisation():
    """Same term count, different lengths: the shorter document should win."""
    index = BM25([
        "blockchain " * 1 + "filler " * 40,
        "blockchain " + "other " * 2,
    ])

    scores = index.score("blockchain")

    assert scores[1] > scores[0]


def test_empty_corpus_is_handled():
    assert BM25([]).score("anything") == []


def test_empty_query_scores_everything_zero():
    assert BM25(DOCS).score("") == [0.0] * len(DOCS)


def test_constant_b_removes_length_normalisation():
    """``b=0`` is the documented way to switch normalisation off."""
    index = BM25(["blockchain " + "filler " * 40, "blockchain other"], b=0.0)

    scores = index.score("blockchain")

    assert scores[0] == pytest.approx(scores[1])


# ── the wrapper ─────────────────────────────────────────────────────────────


def test_wrapper_matches_the_index():
    assert bm25_scores("identity", DOCS) == pytest.approx(BM25(DOCS).score("identity"))


def test_wrapper_parameters_reach_the_index():
    """k1 and b must actually be applied, not silently dropped."""
    long_doc = "blockchain " + "filler " * 40
    short_doc = "blockchain other"

    normalised = bm25_scores("blockchain", [long_doc, short_doc], b=0.75)
    unnormalised = bm25_scores("blockchain", [long_doc, short_doc], b=0.0)

    assert normalised[0] != pytest.approx(unnormalised[0])


def test_average_length_is_the_corpus_average():
    index = BM25(["a b c", "d e", "f"])

    assert index.avg_length == pytest.approx(2.0)
