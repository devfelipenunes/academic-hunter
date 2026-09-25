"""O sdist é o artefato que ninguém despublica: o PyPI não apaga release."""

import pathlib
import re

PYPROJECT = pathlib.Path(__file__).resolve().parent.parent / "pyproject.toml"

SDIST_MARKER = "[tool.hatch.build.targets.sdist]"

AGENT_RUNTIMES = (".claude", ".gemini", ".cursor", ".codex")


def _sdist_excludes() -> list[str]:
    pyproject = PYPROJECT.read_text(encoding="utf-8")
    assert SDIST_MARKER in pyproject, f"{SDIST_MARKER} sumiu — o sdist não tem mais exclusão"
    section = pyproject.split(SDIST_MARKER, 1)[1].split("\n[", 1)[0]
    return [line.strip().rstrip(",").strip('"') for line in section.splitlines() if line.strip().startswith('"')]


def test_the_sdist_never_ships_a_config_file():
    excludes = _sdist_excludes()
    assert any(pattern in ("config*.json", "/config*.json") for pattern in excludes), excludes


def test_the_config_exclusion_is_anchored_to_the_root():
    """Unanchored, `config*.json` also stripped the packaged neutral default.

    Measured: with the unanchored pattern the file was absent from the sdist and
    from the wheel — `python -m build` builds the wheel from the sdist, so one
    exclusion here costs both artifacts — and the symptom was a
    FileNotFoundError on the first tool call of an installed package only.
    """
    excludes = _sdist_excludes()
    config_patterns = [p for p in excludes if p.endswith("config*.json")]

    assert config_patterns, excludes
    assert all(p.startswith("/") for p in config_patterns), (
        "o padrão precisa ser ancorado na raiz, senão alcança "
        "src/academic_hunter/core/infra/config.default.json"
    )


def _matches(pattern: str, path: str) -> bool:
    """gitignore matching, for the subset this exclusion list uses.

    The rule that matters: `*` does not cross a `/`, so `/config*.json` reaches a
    root-level `config.json` and not one under `src/`. `fnmatch` crosses it, and
    simulating with `fnmatch` reports the packaged default as excluded when it is
    not — a test that fails on correct code is worse than no test.
    """
    anchored = pattern.startswith("/")
    body = "".join(
        "[^/]*" if char == "*" else re.escape(char) for char in pattern.lstrip("/")
    )
    if anchored:
        return re.fullmatch(body, path) is not None
    return re.search(r"(^|/)" + body + r"$", path) is not None


def _sdist_keeps(relative: str) -> bool:
    """Whether the exclusion list leaves ``relative`` in the archive."""
    kept = True
    for pattern in _sdist_excludes():
        if pattern.startswith("!"):
            if _matches(pattern[1:], relative):
                kept = True
        elif _matches(pattern, relative):
            kept = False
    return kept


def test_the_packaged_default_survives_the_exclusion_list():
    """The file the server falls back to has to be in the archive that ships it.

    Measured on the real build, not inferred: with the unanchored pattern the
    wheel had no `config.default.json`, so an installed server raised
    FileNotFoundError on its first tool call — the exact install path this is
    meant to make easy.
    """
    assert _sdist_keeps("src/academic_hunter/core/infra/config.default.json")


def test_the_exclusion_list_still_removes_the_users_config():
    """The anchoring must not have defanged the exclusion it was added to."""
    assert not _sdist_keeps("config.json")
    assert not _sdist_keeps("config.local.json")
    assert _sdist_keeps("config.example.json")


def test_the_sdist_never_ships_local_agent_wiring():
    excludes = _sdist_excludes()
    missing = [runtime for runtime in AGENT_RUNTIMES if runtime not in excludes]
    assert not missing, f"{missing} seriam publicados; exclusões: {excludes}"


def test_the_example_config_survives_the_wildcard_that_excludes_the_real_one():
    excludes = _sdist_excludes()
    assert any(p.startswith("!") and p.endswith("config.example.json") for p in excludes), excludes
    assert excludes.index("!/config.example.json") > excludes.index("/config*.json")


def test_the_sdist_never_ships_a_generated_mcp_config():
    """`.mcp.json` was published with the author's absolute path inside it.

    `config*.json` did not cover it and `install.py` did not know about it, so
    the archive carried a client config pointing at a path no user has — the
    same defect as `config.json`, one extension over. The `.example` templates
    are the versioned half and stay in.
    """
    excludes = _sdist_excludes()

    assert ".mcp.json" in excludes
    assert "!.codex/config.toml.example" in excludes
    assert excludes.index("!.codex/config.toml.example") > excludes.index(".codex")


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
        path.read_text(encoding="utf-8", errors="replace") for path in (PYPROJECT.parent / "src").rglob("*.py")
    )
    unused = [
        name
        for name in declared
        if not re.search(rf"^\s*(import|from)\s+{re.escape(name.replace('-', '_'))}\b", source, re.M)
    ]

    assert not unused, f"declared and never imported: {unused}"
