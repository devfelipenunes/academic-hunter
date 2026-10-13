"""A title that arrives with its own field name glued to the front.

One source handed back "Title: Distributed Ledger Technology (DLT) and IT
Governance..." while another handed the same paper without the label. The label
survives into the identity -- ``title_slug`` folds the first to
``titledistributedledger...`` and the second to ``distributedledger...`` -- so
the two never match and the run keeps both copies. Measured: one such pair in a
78-paper blockchain run.

The label is removed only when it stands alone at the very front. A title that
merely contains the word is a title, and truncating it would be the worse of the
two faults.
"""

from academic_hunter.core.models.paper import Paper
from academic_hunter.core.models.utils import strip_title_label
from academic_hunter.core.nlp.scorer import title_slug


def test_the_label_is_removed():
    assert strip_title_label("Title: Distributed Ledger Technology") == "Distributed Ledger Technology"


def test_the_label_is_case_insensitive_and_any_separator():
    for raw in ("TITLE: X", "title - X", "Title — X", "  title:X  "):
        assert strip_title_label(raw) == "X", raw


def test_a_title_that_merely_contains_the_word_is_left_alone():
    for raw in ("The Title of the Paper", "Titles and Abstracts in DLT", "A title: a study"):
        assert strip_title_label(raw) == raw, raw


def test_a_bare_label_without_a_separator_is_not_stripped():
    assert strip_title_label("Title Blockchain") == "Title Blockchain"


def test_stripping_leaves_the_whitespace_collapsed():
    assert strip_title_label("Title:  Two   spaces") == "Two spaces"


def test_it_is_idempotent():
    once = strip_title_label("Title: X Y")
    assert strip_title_label(once) == once


def test_the_label_cannot_change_the_dedup_key():
    """The property the whole thing exists for: both spellings key the same paper."""
    labelled = strip_title_label("Title: Distributed Ledger Technology (DLT) and IT Governance")
    plain = strip_title_label("Distributed Ledger Technology (DLT) and IT Governance")
    assert title_slug(labelled) == title_slug(plain)


def test_constructing_a_paper_strips_the_label():
    """Through the real path -- FIELD_SCHEMA's normalizer, not the helper alone."""
    assert Paper({"Title": "Title: X Y"})["Title"] == "X Y"
    assert Paper({"Title": "X Y"})["Title"] == "X Y"
