"""The record formats, rendered once for both callers that need them.

These tests live here rather than beside the MCP tool because the functions do:
the same ``render_bibtex`` produces the run's own ``academic_dataset_*.bib`` and
the file ``export_report`` hands the agent. The cases below moved from
``tests/interfaces/mcp/test_internal_helpers.py`` when the tool stopped having
private writers of its own.
"""

import csv
import io
import json

from academic_hunter.core.writing.renderers import (
    render_bibtex,
    render_csv,
    render_json,
    render_ris,
)


def test_bibtex_renders_one_entry_per_paper():
    papers = [
        {"Title": "Paper One", "DOI": "10.1000/one", "Authors": "Author A", "Year": 2024},
    ]

    content = render_bibtex(papers)

    assert "@article{" in content
    assert "Paper One" in content
    assert "Author A" in content
    assert "2024" in content


def test_a_paper_with_every_field_empty_still_renders_a_parseable_entry():
    """An entry with no fields is not a reason to write nothing at all."""
    papers = [
        {
            "Title": "",
            "DOI": "",
            "Authors": "",
            "Year": "",
            "Source": "",
            "URL": "",
            "Abstract": "",
        },
    ]

    content = render_bibtex(papers)

    assert content.startswith("@article{")
    assert content.rstrip().endswith("}")


def test_a_paper_with_no_doi_keeps_the_key_the_agent_was_told_to_cite():
    from academic_hunter.core.writing import format_bibtex_key

    papers = [{"Title": "No DOI Paper", "Year": "2024"}]

    expected = format_bibtex_key("No DOI Paper", "2024")

    assert render_bibtex(papers).startswith(f"@article{{{expected},")


def test_an_absent_year_is_not_replaced_by_one():
    """The pipeline used to write the run's ``start_year`` as the paper's.

    ``year = {2021}`` for a paper no source dated is a fabricated citation, and
    it reaches the bibliography of whatever is written from this file.
    """
    papers = [{"Title": "Undated", "DOI": "10.1/u", "Year": ""}]

    content = render_bibtex(papers)
    ris = render_ris(papers)

    assert "2021" not in content
    assert "year = " not in content
    assert "PY  - " not in ris


def test_a_year_is_truncated_only_when_it_starts_with_four_digits():
    assert "year = {2024}" in render_bibtex([{"Title": "a", "Year": "2024-05-01"}])
    assert "year = " not in render_bibtex([{"Title": "a", "Year": "N/A"}])


def test_ris_renders_one_record_per_paper():
    papers = [
        {"Title": "Paper One", "DOI": "10.1000/one", "Authors": ["Author A"], "Year": 2024},
    ]

    content = render_ris(papers)

    assert "TY  - JOUR" in content
    assert "TI  - Paper One" in content
    assert "DO  - 10.1000/one" in content
    assert "PY  - 2024" in content


def test_ris_accepts_a_single_author_written_as_a_string():
    assert "AU  - Single Author" in render_ris([{"Title": "Paper", "Authors": "Single Author"}])


def test_the_abstract_travels_under_the_tag_the_run_has_always_written():
    """``N2`` and ``AB`` both name the abstract, and the two writers disagreed.

    The tool wrote ``AB`` and the pipeline ``N2``, so the same run produced two
    files a reader could tell apart. ``N2`` is the one the run's exporters have
    always emitted, and it is what the escaping tests allow.
    """
    content = render_ris([{"Title": "a", "Abstract": "An abstract."}])

    assert "N2  - An abstract." in content
    assert "AB  - " not in content


def test_nothing_to_render_writes_nothing():
    assert render_bibtex([]) == ""
    assert render_ris([]) == ""
    assert render_json([]) == "[]"


def test_an_empty_dataset_still_carries_its_header():
    """A reader that takes columns by position reads the same table either way."""
    from academic_hunter.core.models.schema import FIELD_SCHEMA

    header = render_csv([]).splitlines()[0].split(",")

    assert header[: len(FIELD_SCHEMA)] == list(FIELD_SCHEMA)


def test_csv_neutralises_a_formula_in_any_column():
    content = render_csv([{"Title": "=cmd|' /C calc'!A0", "Year": 2024}])

    assert "'=cmd" in content


def test_csv_counts_the_databases_and_flags_the_abstracts():
    """Read back through a parser: a ``Source`` of "A, B" carries a comma of its own."""
    papers = [
        {"Title": "Two sources", "Source": "OpenAlex, Crossref", "Abstract": "text"},
        {"Title": "None", "Source": "", "Abstract": ""},
    ]

    rows = list(csv.reader(io.StringIO(render_csv(papers))))
    columns = rows[0]
    by_title = {row[columns.index("Title")]: row for row in rows[1:]}

    assert by_title["Two sources"][columns.index("Database_Count")] == "2"
    assert by_title["None"][columns.index("Database_Count")] == "1"
    assert by_title["Two sources"][columns.index("Has_Abstract")] == "True"
    assert by_title["None"][columns.index("Has_Abstract")] == "False"


def test_json_round_trips_the_rows():
    papers = [{"Title": "Paper One", "Year": 2024}]

    assert json.loads(render_json(papers))[0]["Title"] == "Paper One"
