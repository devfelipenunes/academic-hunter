"""Reading a finished run back off disk.

Not a fallback: every tool call builds its own hunter, whose results are empty.
Was broken in two independent ways, one test each.
"""

from unittest.mock import patch

from academic_hunter.interfaces.mcp.tools._utils import _load_latest_papers


def write_run(root, name="run_20260101_000000", rows=("Title,DOI", "Paper One,10.1/one")):
    """A run directory shaped exactly like the one `CsvExporter` writes."""
    run_dir = root / "results" / name
    run_dir.mkdir(parents=True)
    csv_file = run_dir / f"academic_dataset_{name.removeprefix('run_')}.csv"
    csv_file.write_text("\n".join(rows) + "\n")
    return csv_file


def load(root):
    with patch(
        "academic_hunter.interfaces.mcp.tools._utils.get_project_root",
        return_value=root,
    ):
        return _load_latest_papers()


def test_finds_a_csv_nested_in_a_run_directory(tmp_path):
    """The regression: a non-recursive glob never saw past ``run_<ts>/``.

    That mismatch is why both tools answered "no results" right after a
    successful search — the data was there, one directory down.
    """
    write_run(tmp_path)

    papers = load(tmp_path)

    assert len(papers) == 1
    assert papers[0]["Title"] == "Paper One"


def test_picks_the_most_recent_run(tmp_path):
    import os
    import time

    write_run(tmp_path, name="run_20260101_000000")
    newer = write_run(tmp_path, name="run_20260202_000000")
    os.utime(newer, (time.time(), time.time()))

    papers = load(tmp_path)

    assert papers[0]["DOI"] == "10.1/one"


def test_empty_cells_become_none_not_nan(tmp_path):
    """pandas turns an empty cell into NaN — a float, not the missing value.

    That is what broke indexing: ``nan`` is truthy-checked as present and
    stringifies to "nan", so Chroma rejected the whole batch with "Expected ID
    to be a str, got nan".
    """
    write_run(tmp_path, rows=("Title,DOI", "Paper One,"))

    papers = load(tmp_path)

    assert papers[0]["DOI"] is None, f"got {papers[0]['DOI']!r}"
    assert papers[0]["Title"] == "Paper One"


def test_a_missing_directory_yields_no_papers(tmp_path):
    assert load(tmp_path) == []


def test_a_corrupt_csv_yields_no_papers_instead_of_raising(tmp_path):
    csv_file = write_run(tmp_path)
    csv_file.write_text('\x00\x00 not,a,csv\n"unclosed')

    assert load(tmp_path) == []


def test_an_empty_run_does_not_resurrect_the_previous_one(tmp_path):
    """`_load_latest_papers` takes the newest CSV in the whole tree.

    A run that qualified nothing used to leave no file at all — the exporters
    skipped an empty list — so this walked back to the previous run's papers and
    handed them over as this run's results. The dataset is now written empty, and
    that empty file is the latest result.

    The exporters' half of this is fixed and tested in
    `tests/plugins/test_exporters_empty_run.py`; this is the reader's half.
    """
    write_run(tmp_path, name="run_20260101_000000", rows=("Title,DOI", "Old Paper,10.1/old"))
    write_run(tmp_path, name="run_20260601_000000", rows=("Title,DOI",))

    assert load(tmp_path) == [], "the previous run's papers came back as this run's"
