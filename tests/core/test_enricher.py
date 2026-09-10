"""Regression tests for the abstract enricher.

The enricher used to write a raw keyword score into ``Relevance_Score`` *after*
the pipeline had rank-normalised every score to [0, 10]. That put two different
scales in the same collection while both were compared against the same
``min_relevance_score`` threshold, so enriched papers systematically outranked
the rest. None of the 385 existing tests covered this module, which is how the
bug survived.
"""

import threading
from unittest.mock import MagicMock

from academic_hunter.core.infra import SearchState
from academic_hunter.core.pipeline.enricher import AbstractEnricher


def _run_enrich(paper: dict, abstract: str = "An abstract fetched by DOI.") -> dict:
    """Run one enrichment pass over a single-paper state and return that paper."""
    state = SearchState()
    state.consolidated_results = {"slug-1": paper}
    enricher = AbstractEnricher(connectors={}, state=state, lock=threading.RLock())
    enricher.fetch_abstract_by_doi = MagicMock(return_value=abstract)
    enricher.enrich()
    return paper


def test_enricher_does_not_write_relevance_score():
    """Scoring is owned by the pipeline — the enricher must not touch the score."""
    paper = {
        "Title": "A paper",
        "Abstract": "",
        "DOI": "10.1000/x",
        "Citations": 3,
        "Relevance_Score": 7.4,
    }
    assert _run_enrich(paper)["Relevance_Score"] == 7.4


def test_enricher_invalidates_component_scores():
    """Cached components must be cleared so they are recomputed over the new text.

    The validator scored this paper against an empty abstract; those cached
    values would otherwise be reused by RecomputeRanksStep and the enrichment
    would have no effect on the score.
    """
    paper = {
        "Title": "A paper",
        "Abstract": "",
        "DOI": "10.1000/x",
        "_kw_score": 2.0,
        "_sem_score": 0.4,
    }
    result = _run_enrich(paper)
    assert result["_kw_score"] is None
    assert result["_sem_score"] is None


def test_enricher_sets_the_abstract():
    paper = {"Title": "A paper", "Abstract": "", "DOI": "10.1000/x"}
    assert _run_enrich(paper)["Abstract"] == "An abstract fetched by DOI."


def test_enricher_skips_papers_without_doi():
    """No DOI means no lookup — the paper is left untouched."""
    paper = {"Title": "A paper", "Abstract": "", "DOI": ""}
    state = SearchState()
    state.consolidated_results = {"slug-1": paper}
    enricher = AbstractEnricher(connectors={}, state=state, lock=threading.RLock())
    enricher.fetch_abstract_by_doi = MagicMock(return_value="should not be used")
    enricher.enrich()
    enricher.fetch_abstract_by_doi.assert_not_called()
    assert paper["Abstract"] == ""


def test_enricher_skips_papers_that_already_have_an_abstract():
    paper = {"Title": "A paper", "Abstract": "Already here.", "DOI": "10.1000/x"}
    state = SearchState()
    state.consolidated_results = {"slug-1": paper}
    enricher = AbstractEnricher(connectors={}, state=state, lock=threading.RLock())
    enricher.fetch_abstract_by_doi = MagicMock(return_value="A different abstract.")
    enricher.enrich()
    enricher.fetch_abstract_by_doi.assert_not_called()
    assert paper["Abstract"] == "Already here."
