"""Um título quebrado em duas linhas vale o mesmo que o mesmo título numa linha.

Os conectores entregam texto como ele veio da API, e o arXiv — como quase todo
Atom — quebra títulos e abstracts com indentação. A normalização trocava `\\n`
por um espaço, o que deixa a **indentação da linha seguinte** no meio do texto.
"""

from academic_hunter.core.models import Paper
from academic_hunter.core.nlp import AcademicScorer

WRAPPED = {
    "Title": "A study of blockchain\n      interoperability",
    "Abstract": "We measure throughput\n        across ledgers.",
}
FLAT = {
    "Title": "A study of blockchain interoperability",
    "Abstract": "We measure throughput across ledgers.",
}


def test_a_title_wrapped_across_lines_has_single_spaces():
    assert Paper(dict(WRAPPED))["Title"] == FLAT["Title"]


def test_an_abstract_wrapped_across_lines_has_single_spaces():
    assert Paper(dict(WRAPPED))["Abstract"] == FLAT["Abstract"]


def test_the_wrap_is_not_carried_into_the_displayed_text():
    """Runs of spaces survive into the CSV, the .bib and the agent's context."""
    title = Paper(dict(WRAPPED))["Title"]

    assert "  " not in title
    assert "\n" not in title


def test_a_two_word_term_split_by_the_wrap_still_matches():
    """The scorer matches terms with a literal space, so the wrap broke the match.

    An anchor or technical term of two words that straddled a line break scored
    zero — the paper dropped out of the anchor filter, or ranked below one that
    happened not to wrap.
    """
    scorer = AcademicScorer(
        anchors={},
        tech_strings={},
        tech_weights={"blockchain interoperability": 5.0},
        context_rules={},
        settings={"title_multiplier": 1.5},
    )

    wrapped = Paper(dict(WRAPPED))["Title"]
    flat = Paper(dict(FLAT))["Title"]

    assert scorer.calculate_score(wrapped, "", 0) == scorer.calculate_score(flat, "", 0)
    assert scorer.calculate_score(flat, "", 0) > 0, "the term matched nothing at all"
