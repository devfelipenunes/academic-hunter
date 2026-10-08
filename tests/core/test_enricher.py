"""Regression tests for the metadata enricher.

The enricher used to write a raw keyword score into ``Relevance_Score`` *after*
the pipeline had rank-normalised every score to [0, 10]. That put two different
scales in the same collection while both were compared against the same
``min_relevance_score`` threshold, so enriched papers systematically outranked
the rest. None of the 385 existing tests covered this module, which is how the
bug survived.

It also used to throw away the citation count it had already downloaded: the
OpenAlex and Crossref DOI lookups return the whole work record and only the
abstract was read from it. The count is now kept, and the batched backfill
reaches the papers no connector could report a count for — with the provenance
of every number written down, because replacing an invisible false zero by an
invisible true one is not an improvement.
"""

import threading
from unittest.mock import MagicMock

from academic_hunter.core.infra import SearchState
from academic_hunter.core.models import Paper
from academic_hunter.core.pipeline.enricher import MetadataEnricher


class FakeResolver:
    """A connector that answers for a DOI and can batch citation counts."""

    SOURCE_NAME = "OpenAlex"
    resolve_priority = 3
    CITATION_CHUNK_SIZE = 50

    def __init__(self, metadata=None, counts=None, raises=False):
        self.metadata = metadata or {}
        self.counts = counts or {}
        self.raises = raises
        self.asked = []

    def resolve_metadata_by_doi(self, doi):
        return dict(self.metadata)

    def fetch_citations_by_dois(self, dois, chunk_size=50):
        self.asked.append(list(dois))
        if self.raises:
            raise RuntimeError("OpenAlex is down")
        return dict(self.counts)


def _enricher(paper, connectors=None, settings=None):
    state = SearchState()
    state.consolidated_results = {"slug-1": paper}
    return (
        MetadataEnricher(
            connectors=connectors or {},
            state=state,
            lock=threading.RLock(),
            settings=settings or {},
        ),
        paper,
    )


def _run_enrich(paper: dict, abstract: str = "An abstract fetched by DOI.") -> dict:
    """Run one enrichment pass over a single-paper state and return that paper."""
    enricher, paper = _enricher(paper)
    enricher.fetch_abstract_by_doi = MagicMock(return_value=abstract)
    enricher.lookup_metadata_by_doi = MagicMock(return_value=({"Abstract": abstract}, "OpenAlex"))
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
    enricher, paper = _enricher(paper)
    enricher.lookup_metadata_by_doi = MagicMock(return_value=({"Abstract": "unused"}, "OpenAlex"))
    enricher.enrich_abstracts()
    enricher.lookup_metadata_by_doi.assert_not_called()
    assert paper["Abstract"] == ""


def test_enricher_skips_papers_that_already_have_an_abstract():
    paper = {"Title": "A paper", "Abstract": "Already here.", "DOI": "10.1000/x"}
    enricher, paper = _enricher(paper)
    enricher.lookup_metadata_by_doi = MagicMock(return_value=({"Abstract": "A different abstract."}, "OpenAlex"))
    enricher.enrich_abstracts()
    enricher.lookup_metadata_by_doi.assert_not_called()
    assert paper["Abstract"] == "Already here."


def test_a_resolved_count_fills_a_zero_and_names_the_source_that_answered():
    """The count came from the lookup, not from the source the paper was fetched from.

    An arXiv paper carries ``Citations: 0`` structurally — its own API has no
    such field — and the credit for the number belongs to whatever answered the
    DOI, never to arXiv.
    """
    paper = {
        "Title": "A paper",
        "Abstract": "",
        "DOI": "10.1000/x",
        "Citations": 0,
        "Source": "ArXiv",
    }
    enricher, paper = _enricher(paper)
    enricher.lookup_metadata_by_doi = MagicMock(
        return_value=({"Abstract": "Text.", "Citations": 75}, "OpenAlex")
    )
    enricher.enrich_abstracts()
    assert paper["Citations"] == 75
    assert paper["Citations_Source"] == "openalex-doi"


def test_a_resolved_count_never_overwrites_a_count_a_connector_reported():
    paper = {"Title": "A paper", "Abstract": "", "DOI": "10.1000/x", "Citations": 12}
    enricher, paper = _enricher(paper)
    enricher.lookup_metadata_by_doi = MagicMock(
        return_value=({"Abstract": "Text.", "Citations": 3}, "OpenAlex")
    )
    enricher.enrich_abstracts()
    assert paper["Citations"] == 12


def test_backfill_resolves_a_false_zero_and_invalidates_the_keyword_score():
    """Without the invalidation the corrected count reaches the report but not the score.

    ``RecomputeRanksStep`` only recomputes ``_kw_score`` when it is ``None``, and
    that score already added ``log10(citations + 1)`` computed against the zero.
    It is also the inclusion predicate, so a false zero would keep deciding
    membership after being corrected.
    """
    paper = {
        "Title": "A paper",
        "Citations": 0,
        "DOI": "10.1000/x",
        "_kw_score": 4.0,
        "_sem_score": 0.2,
    }
    connector = FakeResolver(counts={"10.1000/x": 75})
    enricher, paper = _enricher(paper, {"openalex": connector})
    summary = enricher.backfill_citations()
    assert paper["Citations"] == 75
    assert paper["Citations_Source"] == "openalex-batch"
    assert paper["_kw_score"] is None
    assert summary["papers_recovered"] == 1
    assert summary["requests"] == 1


def test_backfill_leaves_a_count_a_connector_reported_alone():
    """Only zeros are asked after, so the source that already answered is not second-guessed."""
    paper = {"Title": "A paper", "Citations": 40, "DOI": "10.1000/x"}
    connector = FakeResolver(counts={"10.1000/x": 900})
    enricher, paper = _enricher(paper, {"openalex": connector})
    enricher.backfill_citations()
    assert paper["Citations"] == 40
    assert connector.asked == []


def test_backfill_asks_about_an_arxiv_url_as_its_datacite_doi():
    """arXiv mints a DataCite DOI, and the connector already carries the arXiv id."""
    paper = {
        "Title": "A paper",
        "Citations": 0,
        "URL": "http://arxiv.org/abs/2107.10243v1",
    }
    connector = FakeResolver(counts={"10.48550/arxiv.2107.10243": 60})
    enricher, paper = _enricher(paper, {"openalex": connector})
    assert connector.asked == []
    enricher.backfill_citations()
    assert connector.asked == [["10.48550/arxiv.2107.10243"]]
    assert paper["Citations"] == 60


def test_a_preprint_whose_other_copy_is_a_landing_page_is_still_asked_about():
    """No DOI here: the merged URL is the only thing the identifier can come from.

    The two copies of this preprint carry an arXiv URL and a CORE landing page,
    and only one of them yields an identifier. Whichever the merge kept decided
    whether the paper was asked about at all -- so the merge, not the paper,
    decided the count.
    """
    arxiv_copy = {
        "Title": "Large Language Model-Powered Smart Contract Vulnerability Detection",
        "Source": "ArXiv",
        "URL": "http://arxiv.org/abs/2310.01152v2",
    }
    core_copy = {
        "Title": "Large Language Model-Powered Smart Contract Vulnerability Detection",
        "Source": "CORE",
        "URL": "https://core.ac.uk/works/391546543",
    }

    merged = Paper(dict(core_copy))
    merged.merge(arxiv_copy, "cat", "cat")

    connector = FakeResolver(counts={"10.48550/arxiv.2310.01152": 9})
    enricher, paper = _enricher(dict(merged), {"openalex": connector})
    enricher.backfill_citations()

    assert connector.asked == [["10.48550/arxiv.2310.01152"]]
    assert paper["Citations"] == 9
    assert paper["Citations_Source"] == "openalex-batch"


def test_backfill_says_which_papers_it_could_not_answer_for():
    """A zero with no source is a different statement from a zero a source confirmed."""
    unresolved = {"Title": "Unresolved", "Citations": 0, "DOI": "10.1000/gone"}
    no_identifier = {"Title": "No identifier", "Citations": 0, "Source": "DOAJ"}
    state = SearchState()
    state.consolidated_results = {"a": unresolved, "b": no_identifier}
    enricher = MetadataEnricher(
        connectors={"openalex": FakeResolver(counts={})},
        state=state,
        lock=threading.RLock(),
        settings={},
    )
    summary = enricher.backfill_citations()
    assert unresolved["Citations_Source"] == "unresolved"
    assert no_identifier["Citations_Source"] == "none"
    assert summary["papers_unresolved"] == 1
    assert summary["papers_without_identifier"] == 1


def test_backfill_never_aborts_the_run_when_the_source_fails():
    paper = {"Title": "A paper", "Citations": 0, "DOI": "10.1000/x"}
    connector = FakeResolver(raises=True)
    enricher, paper = _enricher(paper, {"openalex": connector})
    summary = enricher.backfill_citations()
    assert paper["Citations"] == 0
    assert paper["Citations_Source"] == "unresolved"
    assert summary["papers_unresolved"] == 1


class FakeBatch:
    """A connector that only batches citation counts, at a stated priority."""

    CITATION_CHUNK_SIZE = 50

    def __init__(self, name, priority, counts=None):
        self.SOURCE_NAME = name
        self.resolve_priority = priority
        self.counts = counts or {}
        self.asked = []

    def fetch_citations_by_dois(self, dois, chunk_size=50):
        self.asked.append(list(dois))
        return dict(self.counts)


def test_the_batch_asks_the_highest_priority_connector_not_the_first_in_the_dict():
    """Dictionary order is the order the connectors were registered in, and it
    says nothing about whose answer to prefer.

    Every other lookup in this class ranks by ``resolve_priority``; this one
    took the first connector in ``self.connectors`` that could batch, so
    registering a source could move a run's citation requests onto it.
    """
    paper = {"Title": "A paper", "Citations": 0, "DOI": "10.1000/x"}
    registered_first = FakeBatch("Zeta", 1, {"10.1000/x": 5})
    preferred = FakeBatch("OpenAlex", 3, {"10.1000/x": 75})

    enricher, paper = _enricher(paper, {"zeta": registered_first, "openalex": preferred})
    enricher.backfill_citations()

    assert registered_first.asked == [], "the lower-priority source was asked instead"
    assert preferred.asked == [["10.1000/x"]]
    assert paper["Citations"] == 75


def test_the_batch_choice_does_not_move_with_the_registration_order():
    """Two sources claiming the same priority still have to rank the same way
    twice, or the counts a run records depend on the order they were built in."""
    counts = []
    for order in (("alpha", "beta"), ("beta", "alpha")):
        paper = {"Title": "A paper", "Citations": 0, "DOI": "10.1000/x"}
        sources = {
            "alpha": FakeBatch("Alpha", 2, {"10.1000/x": 11}),
            "beta": FakeBatch("Beta", 2, {"10.1000/x": 22}),
        }
        enricher, paper = _enricher(paper, {name: sources[name] for name in order})
        enricher.backfill_citations()
        counts.append(paper["Citations"])

    assert counts == [11, 11], (
        f"the count this run recorded follows the registration order: {counts}"
    )


def test_a_batch_connector_that_declares_no_priority_is_still_asked():
    """The capability is opt-in, so having it is the permission to ask and the
    priority only orders. Dropping a source over a missing number would be
    silent: the backfill reports nothing was asked of anyone.
    """
    paper = {"Title": "A paper", "Citations": 0, "DOI": "10.1000/x"}
    unranked = FakeBatch("Unranked", 0, {"10.1000/x": 9})

    enricher, paper = _enricher(paper, {"unranked": unranked})

    assert enricher.backfill_citations()["papers_recovered"] == 1
    assert unranked.asked == [["10.1000/x"]]


def test_backfill_is_inert_without_a_connector_that_can_batch():
    class OnlyResolves:
        SOURCE_NAME = "Crossref"
        resolve_priority = 2

        def resolve_metadata_by_doi(self, doi):
            return {}

    paper = {"Title": "A paper", "Citations": 0, "DOI": "10.1000/x"}
    enricher, paper = _enricher(paper, {"crossref": OnlyResolves()})
    assert enricher.backfill_citations() == {}
    assert paper["Citations"] == 0
    assert paper.get("Citations_Source", "") == ""


def test_backfill_can_be_switched_off_by_configuration():
    paper = {"Title": "A paper", "Citations": 0, "DOI": "10.1000/x"}
    connector = FakeResolver(counts={"10.1000/x": 75})
    enricher, paper = _enricher(
        paper, {"openalex": connector}, settings={"citations_backfill": False}
    )
    assert enricher.backfill_citations() == {}
    assert paper["Citations"] == 0
    assert connector.asked == []


def test_backfill_honours_the_enabled_key_the_configuration_documents():
    """``citations_backfill.enabled`` is the switch users are told to use.

    Only a bare ``false`` was read, so writing the documented key disabled
    nothing: the backfill ran, spent its requests and rewrote the counts of a run
    whose author had asked it not to.
    """
    paper = {"Title": "A paper", "Citations": 0, "DOI": "10.1000/x"}
    connector = FakeResolver(counts={"10.1000/x": 75})
    enricher, paper = _enricher(
        paper, {"openalex": connector}, settings={"citations_backfill": {"enabled": False}}
    )

    assert enricher.backfill_citations() == {}
    assert paper["Citations"] == 0
    assert connector.asked == []


def test_an_explicitly_enabled_backfill_still_runs():
    """The default and the documented switch agree, so a run that opts in is not silently inert."""
    paper = {"Title": "A paper", "Citations": 0, "DOI": "10.1000/x"}
    connector = FakeResolver(counts={"10.1000/x": 75})
    enricher, paper = _enricher(
        paper, {"openalex": connector}, settings={"citations_backfill": {"enabled": True}}
    )

    assert enricher.backfill_citations()["papers_recovered"] == 1
    assert paper["Citations"] == 75
