"""O instalador automático precisa concordar com o que o projeto declara.

Ele é o caminho que o `docs/mcp_setup.md` recomenda, então é a primeira coisa que
um usuário novo executa — e o que ele produz silenciosamente é o que esse usuário
vai ter.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _installer():
    spec = importlib.util.spec_from_file_location(
        "academic_hunter_installer", ROOT / "install.py"
    )
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


def test_the_install_asks_for_the_extras_that_are_not_optional():
    """A bare `-e .` leaves `pypdf` out and the PDF leg of full-text does nothing.

    The tools that need it do not fail; they report that they found nothing.
    """
    requirement = _installer().install_command()[-1]

    assert requirement.startswith(".[")
    assert "fulltext" in requirement
