"""How a configured term is matched inside a title or an abstract.

The term list is the user's own vocabulary, and a good part of it is not words:
``c++``, ``c#``, ``.net``, ``node.js``. A match boundary has to accommodate
them, or the term is configured, stored, reported in the run's config and never
once matched.

``\\b`` asserts a word character on *both* sides of the position. Where the term
itself ends in a non-word character that assertion is unsatisfiable, and the
term silently becomes unreachable.
"""

import pytest

from academic_hunter.core.nlp import AcademicScorer
from academic_hunter.core.nlp.scorer import _term_pattern


def matches(term: str, text: str) -> bool:
    return bool(_term_pattern(term).search(text.lower()))


@pytest.mark.parametrize("term, text", [
    ("c++", "we benchmark c++ against the alternatives"),
    ("c++", "C++ is the implementation language"),
    ("c#", "implemented in c# on the runtime"),
    ("c#", "C# was chosen for the prototype"),
    (".net", ".NET is the framework"),
    (".net", "we use .NET daily"),
    ("asp.net", "built on ASP.NET"),
    ("node.js", "written for node.js"),
    ("f#", "a small f# script"),
])
def test_a_term_is_found_wherever_it_is_written(term, text):
    assert matches(term, text), f"{term!r} was unreachable in {text!r}"


@pytest.mark.parametrize("term, text", [
    ("latency", "improving latencies"),
    ("blockchain", "blockchains and distributed ledgers"),
    ("chain", "blockchain"),
    ("ledger", "ledgers"),
])
def test_a_word_term_still_requires_a_word_boundary(term, text):
    """Loosening the guard must not turn every term into a substring search."""
    assert not matches(term, text), f"{term!r} leaked into {text!r}"


def test_a_word_term_still_matches_as_a_word():
    assert matches("latency", "low latency is good")


def test_a_non_word_term_reaches_the_score():
    """The defect showed up as a score, so it is asserted as one.

    A paper titled around C++ scored nothing at all, and the reason was two
    layers away from where anyone would look.
    """
    scorer = AcademicScorer(
        anchors={},
        tech_strings={},
        tech_weights={"c++": 5.0},
        context_rules={},
        settings={"title_multiplier": 1.5, "score_precision": 1},
    )

    assert scorer.calculate_score("Modern C++ design", "A study of the language.") > 0.0


def test_a_non_word_term_is_reported_as_matched():
    """`find_matching_terms` writes the run's matched-anchors column."""
    scorer = AcademicScorer(
        anchors={"Language": ["c++", "c#"]},
        tech_strings={},
        tech_weights={},
        context_rules={},
        settings={},
    )

    found = scorer.find_matching_terms("A paper about C++ and C#.", ["c++", "c#"])

    assert "c++" in found and "c#" in found
