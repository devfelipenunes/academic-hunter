"""Como instalar está descrito em seis arquivos, e nada comparava as cópias.

Cada vez que o fluxo mudou, algumas foram atualizadas e outras não — o
`install.py` instalava `.[fulltext]` enquanto o Dockerfile e o Makefile
instalavam `ml`, e o `docs/index.html` anunciava um comando que não existe.

Estes testes casam texto, não semântica. Eles impedem que *esta* divergência
volte; não provam que as cópias são equivalentes. Uma sétima cópia num arquivo
fora das listas abaixo passa, e um bloco reescrito com outras palavras mas ainda
coerente também. É o preço de comparar seis arquivos com formatos diferentes, e
é mais honesto do que fingir que o problema está resolvido.
"""

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: The prose that describes how to install. Strict: every project-install line in
#: these has to name the extras.
CANONICAL_DOCS = ("README.md", "docs/tutorial.md", "CONTRIBUTING.md", "docs/mcp_setup.md")

#: The pages that must not contradict it. Looser on purpose — the HTML pages show
#: `python install.py` and never name the extras, so demanding the canonical
#: string there would be false.
ALL_DOCS = (*CANONICAL_DOCS, "docs/index.html", "docs/mcp/index.html", "docs/presentation/index.html")

#: Commands that do not exist. `pyproject.toml` declares exactly one script,
#: `academic-mcp`; `academic-hunter` was the interactive CLI, since removed.
BANNED_FORMS = ("academic-hunter --limit",)


def _installer():
    spec = importlib.util.spec_from_file_location("academic_hunter_installer", ROOT / "install.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _project_install_lines(text: str) -> list[str]:
    """The `pip install` lines that install *this* project, not some other package."""
    return [
        line for line in text.splitlines() if "pip install" in line and ("academic-hunter" in line or '-e ".[' in line)
    ]


def _uvx_lines(text: str) -> list[str]:
    """The `uvx --from` invocations, which `_project_install_lines` never sees."""
    return [line for line in text.splitlines() if "uvx --from" in line]


def _named_extras(line: str) -> set[str]:
    """The extras on an install line, as a set.

    A set, not the literal `".[ml,fulltext]"`: `README.md` installs from
    `git+https://`, where the extras live inside the URL's brackets
    (`"academic-hunter[ml,fulltext] @ git+..."`) and the canonical string never
    appears at all.
    """
    extras: set[str] = set()
    for group in re.findall(r"\[([a-z0-9,\s_-]+)\]", line):
        extras.update(part.strip() for part in group.split(",") if part.strip())
    return extras


def test_every_install_doc_names_the_same_extras():
    """The divergence came back four times because nothing compared the copies."""
    canonical = set(_installer().DEFAULT_EXTRAS)

    for name in CANONICAL_DOCS:
        lines = _project_install_lines((ROOT / name).read_text(encoding="utf-8"))

        assert lines, f"{name} no longer says how to install the project"
        for line in lines:
            missing = canonical - _named_extras(line)
            assert not missing, f"{name} installs without {sorted(missing)}: {line.strip()}"


def test_every_uvx_copy_names_the_same_extras():
    """The `uvx` line is the one a reader copies verbatim, and nothing compared it.

    `_project_install_lines` matches `pip install` only, so the published-install
    line in the HTML pages was checked by nothing — and
    `docs/presentation/index.html` went on advertising `[ml,fulltext]`, the
    3.15 GB form, while every other copy said `[fulltext]`.

    Exact equality, not containment: the other tests use `_named_extras`, where a
    superset passes, so `[ml,fulltext]` satisfied them. Measured — this test was
    written with containment first and the drifted page still passed. A `uvx`
    line is the published install, so it names the default and nothing else; the
    opt-in belongs in prose, and a dev install from `git+https` uses `pip`.
    """
    canonical = set(_installer().DEFAULT_EXTRAS)

    for name in ALL_DOCS:
        text = (ROOT / name).read_text(encoding="utf-8")

        for line in _uvx_lines(text):
            extras = _named_extras(line)
            assert extras == canonical, (
                f"{name} publishes a uvx install with {sorted(extras)}, "
                f"not {sorted(canonical)}: {line.strip()}"
            )


def test_no_doc_installs_the_project_without_extras():
    """A bare `pip install -e .` is how the ML stack went missing.

    The tools that need it do not fail — they report that they found nothing,
    which is the failure mode the whole extras discussion exists to prevent.
    """
    for name in ALL_DOCS:
        text = (ROOT / name).read_text(encoding="utf-8")

        for line in _project_install_lines(text):
            assert _named_extras(line), f"{name} installs with no extras: {line.strip()}"


def test_no_doc_advertises_a_command_that_does_not_exist():
    """`docs/index.html` told readers to run a console script that was removed."""
    for name in ALL_DOCS:
        text = (ROOT / name).read_text(encoding="utf-8")
        found = [form for form in BANNED_FORMS if form in text]

        assert not found, f"{name} still advertises {found}"


def test_the_versioned_mcp_configs_link_back_to_the_guide():
    """The guide was an orphan: nothing in the repository linked to it.

    A connection guide nobody is sent to is a guide nobody reads, and every
    client entry point that was documented elsewhere had drifted from the code.
    """
    linked = [
        name
        for name in ("README.md", "docs/tutorial.md")
        if "mcp_setup.md" in (ROOT / name).read_text(encoding="utf-8")
    ]

    assert linked == ["README.md", "docs/tutorial.md"], f"only {linked} link to the guide"
