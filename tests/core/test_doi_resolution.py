"""O DOI arXiv que o pipeline já calculava, gravado em vez de descartado.

Medição no run entregue: 109 dos 310 papers são arXiv-only, com a coluna `DOI`
vazia e um id arXiv no `URL`. O `_citation_key` do enricher derivava o DOI
DataCite desse id — para perguntar a uma fonte as contagens de citação — e
descartava-o. O identificador era conhecido e a coluna ficava vazia.
"""

import threading
from types import SimpleNamespace

import pytest

from academic_hunter.core.models.utils import doi_from_url
from academic_hunter.core.pipeline.steps import ResolveDoiStep


@pytest.mark.parametrize(
    "url,expected",
    [
        ("http://arxiv.org/abs/2310.01152v2", "10.48550/arxiv.2310.01152"),
        ("https://arxiv.org/abs/2310.01152", "10.48550/arxiv.2310.01152"),
        ("https://arxiv.org/pdf/2107.10243v3", "10.48550/arxiv.2107.10243"),
        ("https://arxiv.org/abs/cs/0701001", "10.48550/arxiv.cs/0701001"),
        ("http://ARXIV.ORG/ABS/2310.01152V2", "10.48550/arxiv.2310.01152"),
    ],
)
def test_the_url_implies_the_datacite_doi(url, expected):
    """A versão cai: `v2` e `v1` são o mesmo trabalho, e a DataCite regista-o uma vez."""
    assert doi_from_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "",
        None,
        "https://core.ac.uk/works/391546543",
        "https://doaj.org/article/abc123",
        "https://example.org/paper/42",
        "doi:10.1234/ledger",
    ],
)
def test_a_url_that_names_nothing_implies_nothing(url):
    """Um DOI inventado a partir de uma landing page é pior do que a coluna vazia."""
    assert doi_from_url(url) == ""


def hunter(papers):
    return SimpleNamespace(
        consolidated_results={str(i): p for i, p in enumerate(papers)},
        lock=threading.RLock(),
        state=SimpleNamespace(stats={}),
    )


def preprint(**overrides):
    return {
        "Title": "Smart contract vulnerability detection",
        "URL": "http://arxiv.org/abs/2310.01152v2",
        "DOI": "",
        "Source": "ArXiv",
        "Year": "2023",
        **overrides,
    }


def test_an_empty_doi_is_filled_from_the_papers_own_url():
    papers = [preprint()]

    ResolveDoiStep(hunter(papers)).run()

    assert papers[0]["DOI"] == "10.48550/arxiv.2310.01152"


def test_a_registered_doi_is_never_replaced():
    """Um DOI de editora endereça a versão publicada; o derivado do URL, o preprint."""
    papers = [preprint(DOI="10.1145/3576915.3623202", URL="http://arxiv.org/abs/2310.01152v2")]

    ResolveDoiStep(hunter(papers)).run()

    assert papers[0]["DOI"] == "10.1145/3576915.3623202"


def test_a_paper_with_no_identifier_is_left_as_it_was():
    papers = [preprint(URL="https://core.ac.uk/works/391546543")]

    ResolveDoiStep(hunter(papers)).run()

    assert papers[0]["DOI"] == ""


def test_the_count_is_reported_rather_than_kept_quiet():
    made = hunter([preprint(), preprint(), {**preprint(), "DOI": "10.1/x"}])

    ResolveDoiStep(made).run()

    assert made.state.stats["doi_resolved"] == 2


def test_running_twice_changes_nothing_the_second_time():
    """Idempotente: a segunda passagem encontra a coluna preenchida e pára."""
    papers = [preprint()]

    ResolveDoiStep(hunter(papers)).run()
    ResolveDoiStep(hunter(papers)).run()

    assert papers[0]["DOI"] == "10.48550/arxiv.2310.01152"
