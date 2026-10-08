"""Tests for core.writing — templates, author style conventions, outline builder."""

import pytest

from academic_hunter.core.writing import (
    build_outline,
    format_bibtex_key,
    format_citation,
    format_equation,
    format_table,
    get_template,
    list_templates,
    paper_citation_key,
)
from academic_hunter.core.writing.outline import PROSE_MARKER, RunData


def test_three_templates_exist():
    keys = {t.key for t in list_templates()}
    assert keys == {"method", "software", "survey"}


def test_unknown_template_lists_valid_keys():
    """The error must let a caller (or an agent) self-correct."""
    with pytest.raises(KeyError, match="method"):
        get_template("nonsense")


def test_method_template_matches_the_reference_manuscript():
    """Section order follows the author's conference manuscript."""
    names = get_template("method").section_names()
    assert names[0] == "Abstract"
    assert names[1] == "Introduction"
    assert "Method" in names
    assert "Related Work" in names
    assert names[-1] == "Conclusion"
    assert names.index("Experiments") < names.index("Related Work")


def test_joss_template_uses_summary_not_abstract():
    names = get_template("software").section_names()
    assert names[0] == "Summary"
    assert "Abstract" not in names
    assert "Statement of Need" in names


def test_survey_template_declares_its_own_limitations():
    names = get_template("survey").section_names()
    assert "Limitations" in names


def test_citation_single():
    assert format_citation(["echo2024"]) == "[@echo2024]"


def test_citation_multiple_preserves_order():
    """The author orders keys deliberately; sorting would lose that."""
    assert format_citation(["queenbee2026", "hybridagentic2026"]) == (
        "[@queenbee2026; @hybridagentic2026]"
    )


def test_citation_tolerates_prefixed_keys():
    assert format_citation(["@echo2024", "[@sgpt2022]"]) == "[@echo2024; @sgpt2022]"


def test_citation_rejects_empty():
    with pytest.raises(ValueError):
        format_citation([])


def test_bibtex_key_from_title():
    """Dominant convention in the existing .bib files: stem + year, lowercase."""
    assert format_bibtex_key("Echo Embeddings", 2024) == "echo2024"
    assert format_bibtex_key("ASReview: Open Source Software", 2020) == "asreview2020"


def test_bibtex_key_skips_leading_stopwords():
    assert format_bibtex_key("A Survey on Blockchain", 2023) == "survey2023"


def test_bibtex_key_prefers_author_when_given():
    assert format_bibtex_key("Repetition Improves Embeddings", 2024, author="Springer") == "springer2024"


def test_bibtex_key_handles_particles_in_author_name():
    """'van de Schoot' -> surname is the last token."""
    assert format_bibtex_key("Title", 2021, author="van de Schoot") == "schoot2021"


def test_bibtex_key_is_alnum_only():
    key = format_bibtex_key("Weight-Bleeding: A Method (2026)", 2026)
    assert key.isalnum()


def test_bibtex_key_reads_a_family_first_author_name():
    """'Schoot, van de' is the same person as 'van de Schoot'."""
    assert format_bibtex_key("Title", 2021, author="Schoot, van de") == "schoot2021"


def test_a_paper_without_a_doi_keeps_the_bare_key():
    paper = {"Title": "Echo chambers in social media", "Year": "2024"}
    assert paper_citation_key(paper) == "echo2024"


def test_a_doi_separates_two_papers_that_share_a_stem_and_year():
    """The collision the allocator used to handle by position."""
    first = {"Title": "Echo chambers in social media", "Year": "2024", "DOI": "10.1/echo-a"}
    second = {"Title": "Echo in the courtroom", "Year": "2024", "DOI": "10.1/echo-b"}

    assert paper_citation_key(first) != paper_citation_key(second)


def test_the_same_doi_always_gives_the_same_suffix():
    """Two callers with no shared state must reach the same key."""
    paper = {"Title": "Echo", "Year": "2024", "DOI": "10.1/echo-a"}
    spelled_out = {**paper, "DOI": "https://doi.org/10.1/ECHO-A"}

    assert paper_citation_key(paper) == paper_citation_key(spelled_out)


def test_the_corpus_lower_case_fields_work_too():
    """The vector store returns `title`/`doi`, the export rows `Title`/`DOI`."""
    from_vector_store = {"title": "Echo", "year": "2024", "doi": "10.1/echo-a"}
    from_export = {"Title": "Echo", "Year": "2024", "DOI": "10.1/echo-a"}

    assert paper_citation_key(from_vector_store) == paper_citation_key(from_export)


def test_table_renders_caption_above_and_right_aligns_numbers():
    out = format_table(
        headers=["Mode", "Identified"],
        rows=[["keyword", 1206], ["embedding", 1016]],
        caption="Ablation study results",
        table_number=2,
    )
    lines = out.splitlines()
    assert lines[0] == "**Table 2: Ablation study results**"
    assert "| Mode | Identified |" in out
    assert "| ---- | ----: |" in out


def test_table_highlights_the_winning_row():
    out = format_table(
        headers=["Mode", "Score"],
        rows=[["a", 1], ["b", 2]],
        highlight_row=1,
    )
    assert "| **b** | **2** |" in out


def test_table_with_footnote_marks_caption_and_explains_below():
    out = format_table(
        headers=["X"], rows=[["1"]], caption="Cap", footnote="Requires an API key."
    )
    assert "**Cap**¹" in out
    assert "¹ Requires an API key." in out


def test_table_rejects_ragged_rows():
    with pytest.raises(ValueError, match="Row 0"):
        format_table(headers=["a", "b"], rows=[["only-one"]])


def test_table_rejects_empty_headers():
    with pytest.raises(ValueError):
        format_table(headers=[], rows=[])


def test_equation_is_block_form_with_where_clause():
    out = format_equation(r"s = \sqrt{\sigma} \times 10", where=r"$\sigma$ is the cosine")
    assert out.startswith("$$")
    assert "where $\\sigma$ is the cosine" in out


def test_equation_does_not_double_the_where_keyword():
    out = format_equation("x = 1", where="where x is a value")
    assert out.count("where") == 1


def _run_data(**overrides) -> RunData:
    base = dict(
        topic="Blockchain interoperability",
        stats={
            "identified": {"OpenAlex": 685, "Crossref": 582},
            "duplicates_removed": 108,
            "excluded_year": 127,
            "excluded_anchors": 833,
            "excluded_technical_score": 75,
            "included_final": 304,
        },
        source_breakdown={"OpenAlex": 685, "Crossref": 582},
        exclusions_by_source={"OpenAlex": {"year": 40, "anchor": 300, "score": 20}},
        papers=[{"Title": f"p{i}"} for i in range(10)],
    )
    base.update(overrides)
    return RunData(**base)


def test_outline_has_frontmatter_and_title():
    out = build_outline(get_template("method"), _run_data())
    assert out.startswith("---")
    assert 'title: "Blockchain interoperability"' in out
    assert "template: method" in out


def test_outline_contains_every_section_of_the_template():
    template = get_template("survey")
    out = build_outline(template, _run_data())
    for name in template.section_names():
        assert "## " in out and name in out


def test_outline_injects_real_screening_numbers():
    """Numbers must come from the run — never invented."""
    out = build_outline(get_template("method"), _run_data())
    assert "Included in final set | 304" in out
    assert "Duplicates removed | 108" in out


def headings(outline):
    """``(level, label, body)`` per heading — by level, not by substring.

    ``"# 2 Method" in outline`` is true of ``"## 2 Method"`` as well, so a
    containment check on the marker alone cannot tell a section from its own
    subsection, which is the only thing the level is there to say.
    """
    blocks = []
    for line in outline.splitlines():
        if line.startswith("#") and " " in line:
            level = len(line) - len(line.lstrip("#"))
            blocks.append([level, line[level:].strip(), []])
        elif blocks:
            blocks[-1][2].append(line)
    return [(level, label, "\n".join(body)) for level, label, body in blocks]


def test_outline_marks_every_leaf_section_for_prose():
    """A table without an interpretation paragraph is data, not an article."""
    template = get_template("method")
    out = build_outline(template, _run_data())
    rendered = {(level, label): body for level, label, body in headings(out)}

    def leaves(sections, depth=1):
        for s in sections:
            if s.subsections:
                yield from leaves(s.subsections, depth + 1)
            else:
                yield s, depth

    for section, depth in leaves(template.sections):
        label = f"{section.number} {section.name}" if section.number else section.name
        assert (depth, label) in rendered, f"heading for {section.name} not found at level {depth}"
        assert PROSE_MARKER in rendered[(depth, label)], f"{section.name} has no prose marker"


def test_a_subsection_sits_below_the_section_that_owns_it():
    """Every heading was `##`, so the nesting the template declares was flat."""
    template = get_template("method")
    out = build_outline(template, _run_data())

    top = [s for s in template.sections if s.subsections][0]
    child = top.subsections[0]

    levels = {label: level for level, label, _ in headings(out)}
    assert levels[f"{top.number} {top.name}"] == 1
    assert levels[f"{child.number} {child.name}"] == 2


def test_outline_never_injects_score_numbers():
    """A guard against the outline silently carrying computed scores.

    Scores are the part of the pipeline whose definition was ambiguous, and the
    outline must not bake them in until that is settled.
    """
    out = build_outline(get_template("method"), _run_data())
    assert "Relevance_Score" not in out


def test_outline_handles_empty_run_data():
    """An outline for a run with no data must still be produced, not crash."""
    out = build_outline(get_template("survey"), RunData(topic="Empty"))
    assert "# Abstract" in out
    assert PROSE_MARKER in out
