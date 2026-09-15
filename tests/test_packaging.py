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


# ── o que o projeto pede para instalar ──────────────────────────────────────


def test_every_dependency_announced_to_the_client_is_real():
    """`FastMCP(dependencies=...)` is a hint the client acts on.

    `bibtexparser` was announced and exists nowhere: not in `pyproject.toml`, not
    in an import, not in the environment. A client that follows the hint spends a
    download on a package this project does not use.
    """
    import importlib

    from academic_hunter.interfaces.mcp.server import create_mcp_server

    server = create_mcp_server()

    assert server.dependencies, "the announcement is empty"
    for name in server.dependencies:
        importlib.import_module(name)  # raises when it is not installed


def test_every_declared_dependency_is_imported_somewhere():
    """A requirement nobody imports is weight every user installs.

    `fastmcp` was one. The code uses `mcp.server.fastmcp`, which comes from the
    `mcp` package — declared separately and actually imported.
    """
    import re

    pyproject = PYPROJECT.read_text(encoding="utf-8")
    block = pyproject.split("dependencies = [", 1)[1].split("]", 1)[0]
    declared = re.findall(r'"([A-Za-z0-9_.-]+)', block)

    assert declared, "no dependencies were parsed out of pyproject.toml"

    source = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in (PYPROJECT.parent / "src").rglob("*.py")
    )
    unused = [
        name
        for name in declared
        if not re.search(rf"^\s*(import|from)\s+{re.escape(name.replace('-', '_'))}\b", source, re.M)
    ]

    assert not unused, f"declared and never imported: {unused}"
