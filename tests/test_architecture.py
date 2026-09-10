"""Architecture tests — enforce the hexagonal boundary mechanically.

The boundary is the whole point of the layout, and it is invisible to ordinary
tests: an import added in the wrong direction works fine and only shows up when
someone tries to swap an adapter. Before this test, ``core`` imported the MCP
tool layer, the exporter registry, the connector registry and ChromaDB
directly. A comment would not have prevented that from creeping back.

Layout::

    interfaces/  (MCP server, tools)      ─┐
    app/         (AcademicHunter, wiring) ─┼─► core/  (domain, ports)
    plugins/     (adapters)               ─┘
"""

import ast
import pathlib

import pytest

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "academic_hunter"
CORE = SRC / "core"

#: Packages ``core`` must never import from.
FORBIDDEN_FROM_CORE = ("academic_hunter.interfaces", "academic_hunter.app", "academic_hunter.plugins")
#: Packages ``plugins`` must never import from (adapters depend on the domain,
#: never on the application layer or the interface layer).
FORBIDDEN_FROM_PLUGINS = ("academic_hunter.interfaces", "academic_hunter.app")


def _resolve(module_path: pathlib.Path, node: ast.ImportFrom) -> str:
    """Resolve an ImportFrom node to an absolute module name.

    Handles relative imports by walking up from the file's own package, so
    ``from ...plugins.connectors import X`` inside ``core/pipeline/steps.py``
    resolves to ``academic_hunter.plugins.connectors``.
    """
    if node.level == 0:
        return node.module or ""

    # Package containing this file, e.g. "academic_hunter.core.pipeline".
    rel = module_path.relative_to(SRC.parent)  # academic_hunter/core/pipeline/steps.py
    package_parts = list(rel.with_suffix("").parts[:-1])

    # level=1 means "this package", so drop (level - 1) components.
    trim = node.level - 1
    base_parts = package_parts[: len(package_parts) - trim] if trim else package_parts
    base = ".".join(base_parts)

    return f"{base}.{node.module}" if node.module else base


def _imports_in(module_path: pathlib.Path) -> list[tuple[str, int]]:
    """Return ``(module, lineno)`` for every import in a Python file."""
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            found.append((_resolve(module_path, node), node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name, node.lineno))
    return found


def _violations(root: pathlib.Path, forbidden: tuple[str, ...]) -> list[str]:
    out = []
    for module_path in sorted(root.rglob("*.py")):
        for module, lineno in _imports_in(module_path):
            if module.startswith(forbidden):
                rel = module_path.relative_to(SRC.parent)
                out.append(f"{rel}:{lineno} imports {module}")
    return out


def test_core_does_not_import_outward():
    """``core`` is the domain: it must not know about adapters or the outside.

    Everything core needs from the outside arrives by injection from the
    composition root (``academic_hunter.app``).
    """
    violations = _violations(CORE, FORBIDDEN_FROM_CORE)

    assert not violations, (
        "core must not import interfaces/, app/ or plugins/ — inject instead:\n  "
        + "\n  ".join(violations)
    )


def test_plugins_do_not_import_interfaces_or_app():
    """Adapters depend on the domain, never on the application or interface layer."""
    violations = _violations(SRC / "plugins", FORBIDDEN_FROM_PLUGINS)

    assert not violations, (
        "plugins must not import interfaces/ or app/:\n  " + "\n  ".join(violations)
    )


def test_ports_declare_no_plugin_dependency():
    """The ports package is the innermost contract and must stay dependency-free."""
    violations = _violations(SRC / "core" / "ports", FORBIDDEN_FROM_CORE)

    assert not violations, "core/ports must not import adapters:\n  " + "\n  ".join(violations)


@pytest.mark.parametrize(
    "module",
    [
        "academic_hunter.core.ports.exporter",
        "academic_hunter.core.ports.screener",
        "academic_hunter.core.ports.vector_store",
        "academic_hunter.core.ports.connector",
    ],
)
def test_ports_are_importable(module):
    """Each port module imports cleanly and exposes its contract."""
    __import__(module)
