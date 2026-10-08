"""A ordenação por pontuação sozinha não é uma ordem total.

Dois runs do mesmo corpus davam 214 linhas trocadas, com ``Relevance_Score``
idêntico paper a paper e zero inversões entre papers de pontuação diferente:
todas as 214 dentro de grupos de empate. Nesse run, 287 dos 310 papers partilham
a pontuação com alguém. A ordem de chegada vem da mineração concorrente, por isso
a posição relativa dentro de um empate variava entre runs.

``paper_order_key`` fecha isso com um segundo elemento — a identidade do paper.
Estes testes fixam as duas propriedades que a chave tem de ter: a ordem entre
pontuações diferentes mantém-se, e dentro de um empate a ordem é sempre a mesma.
"""

import math

from academic_hunter.core.models.utils import paper_order_key


def test_a_higher_score_comes_first():
    high = {"Title": "High", "Relevance_Score": 9.0}
    low = {"Title": "Low", "Relevance_Score": 3.0}

    assert paper_order_key(high) < paper_order_key(low)


def test_a_tie_is_broken_by_the_doi():
    a = {"Title": "Same", "DOI": "10.1/a", "Relevance_Score": 4.0}
    b = {"Title": "Same", "DOI": "10.1/b", "Relevance_Score": 4.0}

    assert paper_order_key(a) < paper_order_key(b)
    assert not paper_order_key(b) < paper_order_key(a)


def test_a_paper_with_no_doi_is_ordered_by_its_title():
    """145 of the 310 papers of the measured run have no DOI.

    A tie-break on the DOI alone would have left almost half the corpus ordered
    by arrival, which is the defect wearing a different hat.
    """
    a = {"Title": "Alpha", "Relevance_Score": 4.0}
    b = {"Title": "Beta", "Relevance_Score": 4.0}

    assert paper_order_key(a) < paper_order_key(b)


def test_a_doi_written_as_a_url_orders_like_the_bare_doi():
    """The same work written two ways must not land in two places.

    This is why ``normalize_doi`` is reused rather than a second identity rule
    invented: two spellings of one DOI would otherwise order apart.
    """
    bare = {"Title": "X", "DOI": "10.1234/abc", "Relevance_Score": 4.0}
    url = {"Title": "X", "DOI": "https://doi.org/10.1234/ABC", "Relevance_Score": 4.0}

    assert paper_order_key(bare)[1] == paper_order_key(url)[1]


def test_the_title_is_compared_as_written_and_not_slugged():
    """A slug merges titles that are not the same title.

    ``title_slug`` drops every non-word character, so these two collapse to one
    string — and two papers with one key fall back on arrival order, which is
    what the key exists to remove.
    """
    hyphen = {"Title": "A-B", "Relevance_Score": 4.0}
    plain = {"Title": "AB", "Relevance_Score": 4.0}

    assert paper_order_key(hyphen) != paper_order_key(plain)


def test_a_numeric_string_score_is_read_as_a_number():
    """A lexical comparison would put "9" above "10" and invert the run."""
    nine = {"Title": "Nine", "Relevance_Score": "9"}
    ten = {"Title": "Ten", "Relevance_Score": "10"}

    assert paper_order_key(ten) < paper_order_key(nine)


def test_an_unusable_score_counts_as_zero():
    for raw in (None, "", "not a score", [], {}):
        assert paper_order_key({"Title": "X", "Relevance_Score": raw})[0] == 0.0

    assert paper_order_key({"Title": "X"})[0] == 0.0


def test_a_non_finite_score_does_not_fall_back_on_arrival_order():
    """``nan`` compares false against everything, so its position was undefined.

    ``float(nan)`` succeeds, so a tolerance that only catches ``TypeError`` and
    ``ValueError`` lets it through and the paper lands wherever it arrived — the
    defect surviving inside its own fix.
    """
    nan = {"Title": "X", "Relevance_Score": float("nan")}
    missing = {"Title": "X"}

    assert paper_order_key(nan) == paper_order_key(missing)
    assert not math.isnan(paper_order_key(nan)[0])
