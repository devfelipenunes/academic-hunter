"""Packaging tests — the sdist is the one artifact that cannot be taken back.

PyPI refuses to delete a release, so whatever is inside a published sdist is
public permanently. The 2.1.0 sdist built in July shipped `config copy.json`
with a live Semantic Scholar key in it, plus the local agent wiring of two other
runtimes. No ``git grep`` would ever have found it: ``dist/`` is ignored, so the
repository looked clean while the tarball was not.

``.gitignore`` protects the repository. It does not protect the tarball, and it
never did — a build backend reads it as a hint, not as a contract. The exclusion
block in ``pyproject.toml`` is the contract, so this test reads that block
instead of rebuilding: ``python -m build`` downloads its backend in an isolated
environment, which would make the suite need the network to check a file list.
"""

import pathlib

PYPROJECT = pathlib.Path(__file__).resolve().parent.parent / "pyproject.toml"

SDIST_MARKER = "[tool.hatch.build.targets.sdist]"

#: Local wiring for the agent runtimes. Each names an absolute path to this
#: machine's interpreter — useless in a clone, and a map of the author's disk.
AGENT_RUNTIMES = (".claude", ".gemini", ".cursor", ".codex")


def _sdist_excludes() -> list[str]:
    """The ``exclude`` patterns of the sdist target, in the order they appear."""
    pyproject = PYPROJECT.read_text(encoding="utf-8")
    assert SDIST_MARKER in pyproject, (
        f"{SDIST_MARKER} is gone — the sdist has no exclusions left, and a config "
        "file with a live key would ship again"
    )
    section = pyproject.split(SDIST_MARKER, 1)[1].split("\n[", 1)[0]
    return [line.strip().rstrip(",").strip('"') for line in section.splitlines() if line.strip().startswith('"')]


def test_the_sdist_never_ships_a_config_file():
    assert "config*.json" in _sdist_excludes()


def test_the_sdist_never_ships_local_agent_wiring():
    excludes = _sdist_excludes()
    missing = [runtime for runtime in AGENT_RUNTIMES if runtime not in excludes]
    assert not missing, f"{missing} would be published; excludes are {excludes}"


def test_the_example_config_survives_the_wildcard_that_excludes_the_real_one():
    """``config*.json`` matches ``config.example.json`` too.

    The negation is what keeps the example — the only config file a clone is
    supposed to have — in the tarball, and it only works *after* the pattern it
    negates. A reordered list would silently drop it, and nothing else would
    notice until a user found no example to copy.
    """
    excludes = _sdist_excludes()
    assert "!config.example.json" in excludes
    assert excludes.index("!config.example.json") > excludes.index("config*.json")
