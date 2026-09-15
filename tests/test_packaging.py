"""O sdist é o artefato que ninguém despublica: o PyPI não apaga release."""

import pathlib

PYPROJECT = pathlib.Path(__file__).resolve().parent.parent / "pyproject.toml"

SDIST_MARKER = "[tool.hatch.build.targets.sdist]"

AGENT_RUNTIMES = (".claude", ".gemini", ".cursor", ".codex")


def _sdist_excludes() -> list[str]:
    pyproject = PYPROJECT.read_text(encoding="utf-8")
    assert SDIST_MARKER in pyproject, f"{SDIST_MARKER} sumiu — o sdist não tem mais exclusão"
    section = pyproject.split(SDIST_MARKER, 1)[1].split("\n[", 1)[0]
    return [line.strip().rstrip(",").strip('"') for line in section.splitlines() if line.strip().startswith('"')]


def test_the_sdist_never_ships_a_config_file():
    assert "config*.json" in _sdist_excludes()


def test_the_sdist_never_ships_local_agent_wiring():
    excludes = _sdist_excludes()
    missing = [runtime for runtime in AGENT_RUNTIMES if runtime not in excludes]
    assert not missing, f"{missing} seriam publicados; exclusões: {excludes}"


def test_the_example_config_survives_the_wildcard_that_excludes_the_real_one():
    excludes = _sdist_excludes()
    assert "!config.example.json" in excludes
    assert excludes.index("!config.example.json") > excludes.index("config*.json")
