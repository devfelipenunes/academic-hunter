"""O instalador automático precisa concordar com o que o projeto declara.

Ele é o caminho que o `docs/mcp_setup.md` recomenda, então é a primeira coisa que
um usuário novo executa — e o que ele produz silenciosamente é o que esse usuário
vai ter.
"""

import importlib.util
import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _installer():
    spec = importlib.util.spec_from_file_location("academic_hunter_installer", ROOT / "install.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("version", [(3, 8, 0), (3, 9, 18)])
def test_a_python_below_the_declared_floor_is_refused(monkeypatch, version):
    """The guard accepted 3.8 while `pyproject.toml` declares `>=3.10`.

    On 3.8 or 3.9 the installer passed its own check and then `pip install -e .`
    failed with a message about the package rather than the interpreter.
    """
    monkeypatch.setattr(sys, "version_info", version)

    with pytest.raises(SystemExit):
        _installer().check_python()


def test_a_supported_python_passes(monkeypatch):
    monkeypatch.setattr(sys, "version_info", (3, 12, 0))

    _installer().check_python()  # must not raise


def test_the_pip_path_does_not_depend_on_the_working_directory():
    """It ran the relative `venv/bin/pip`, and looked for `Path("venv")`.

    Invoked as `python /path/to/install.py` from anywhere else, it either failed
    to find pip or created a second virtualenv in the caller's directory.
    """
    installer = _installer()

    assert installer.venv_dir().is_absolute()
    assert installer.pip_executable().is_absolute()


def test_the_install_asks_for_the_extra_the_search_needs():
    """A bare `-e .` leaves `pypdf` out and the PDF leg of full-text does nothing.

    The tools that need it do not fail; they report that they found nothing.
    `ml` is deliberately absent here: the search does not need it, and it is the
    3.15 GB download. See `test_ml_asks_for_the_analysis_stack`.
    """
    requirement = _installer().install_command()[-1]

    assert requirement.startswith(".[")
    assert "fulltext" in requirement
    assert "ml" not in requirement


def test_the_installer_survives_a_run_with_no_terminal(monkeypatch):
    """`install.py < /dev/null` raised EOFError, *after* creating the venv.

    The Claude Desktop prompt was unconditional, so every unattended run — CI,
    Docker, a provisioning script — died halfway with the install already on
    disk, which is worse than not starting.
    """
    installer = _installer()
    monkeypatch.setattr(sys, "stdin", io.StringIO())  # isatty() is False

    assert installer.install_mcp_claude_desktop() is False


def test_ml_is_opt_in_and_never_the_default():
    """`ml` pulls torch — 3.15 GB measured on Linux, ~2.5 GB of it CUDA.

    A CPU-only user should never pay that without asking: the documented install
    leaves it out, and the screener embeds with ChromaDB's ONNX model instead.
    """
    assert _installer().install_command()[-1] == ".[fulltext]"


def test_ml_asks_for_the_analysis_stack():
    """`--ml` is the one path that carries the 3.15 GB, so it must name both."""
    assert _installer().install_command(ml=True)[-1] == ".[ml,fulltext]"


def test_the_uv_check_is_advisory_and_never_fatal(monkeypatch, capsys):
    """This script installs the clone; `uv` is what installs the published one.

    Making it fatal would refuse to install where the venv path works perfectly,
    so a machine without `uv` has to walk through the check and out the other
    side — told what it is missing, not stopped.
    """
    installer = _installer()
    monkeypatch.setattr(installer.shutil, "which", lambda name: None)

    installer.check_uv()  # must not raise or exit

    printed = capsys.readouterr().out
    assert "uv is not on PATH" in printed
    assert "astral.sh/uv" in printed, "the reader is told uv is missing, not how to get it"


def test_the_uvx_alternative_reaches_the_reader_without_installing_uv():
    """The whole point of the published path is that it is one command.

    A reader who ran the clone installer should still see it, since that is the
    shape `docs/mcp_setup.md` documents first — and `--from` is not optional:
    the distribution is `academic-hunter`, the script is `academic-mcp`.
    """
    installer = _installer()

    assert installer.UVIX_COMMAND in "\n".join(installer.NEXT_STEPS_UVX)


def test_the_printed_uvx_command_matches_the_canonical_guide():
    """`docs/mcp_setup.md` is the canonical copy; the installer only echoes it.

    Three places now print this command — the guide, the README and here — and
    a drifted copy is a command that resolves to nothing.
    """
    installer = _installer()
    guide = (ROOT / "docs" / "mcp_setup.md").read_text(encoding="utf-8")

    assert installer.UVIX_COMMAND in guide
    assert installer.UVIX_COMMAND in (ROOT / "README.md").read_text(encoding="utf-8")


MCP_EXAMPLES = (".mcp.json.example", ".codex/config.toml.example")

#: The path the versioned templates carry. A placeholder on purpose: any real
#: absolute path is correct in exactly one checkout.
PLACEHOLDER = "/absolute/path/to/academic-hunter"

#: Prefixes of a path that names somebody's machine.
FOREIGN_ROOTS = ("/home/", "/Users/", "/l/disk0", "/opt/", "C:\\")


def test_no_committed_mcp_config_hardcodes_a_machine_path():
    """Both versioned configs pointed at the machine of whoever committed them.

    `.mcp.json` and `.codex/config.toml` carried a
    `.../me/pesquisa_academica/venv/bin/academic-mcp` that exists in no other
    clone, and nothing generated them. The client's only symptom is a generic
    "failed to connect", which is indistinguishable from a broken server.
    """
    for name in MCP_EXAMPLES:
        text = (ROOT / name).read_text(encoding="utf-8")

        assert PLACEHOLDER in text, f"{name} lost the documented placeholder"
        foreign = [root for root in FOREIGN_ROOTS if root in text]
        assert not foreign, f"{name} hardcodes a machine path: {foreign}"


def test_the_mcp_command_is_derived_from_the_project_root():
    """The command was a literal, so it travelled between machines.

    An absolute path written by hand works in exactly one checkout — and the
    working configs are not tracked, so the placeholder has to be substituted
    from something this process actually knows.
    """
    command = Path(_installer().mcp_server_entry()["command"])

    assert command.is_absolute()
    assert ROOT in command.parents


def test_the_generated_config_names_this_checkout_not_the_placeholder():
    """The template is a mold; the written file has to name this machine."""
    installer = _installer()

    for name in MCP_EXAMPLES:
        rendered = installer.render_client_config(ROOT / name)

        assert installer.mcp_server_command() in rendered
        assert installer.MCP_COMMAND_PLACEHOLDER not in rendered
