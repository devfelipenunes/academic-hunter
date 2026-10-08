"""Application layer — orchestration and composition.

This is where the domain meets its adapters. ``AcademicHunter`` is the
composition root: it is the only place that imports concrete plugins and wires
them into the domain, which is why it lives outside ``core``.

Layering::

    interfaces/  (MCP server, tools)     ─┐
    app/         (AcademicHunter, wiring) ─┼─► core/  (domain, ports)
    plugins/     (adapters)              ─┘

``core`` depends on nothing outward: it defines the ports in ``core/ports``
and receives implementations by injection. ``plugins`` implement those ports.
``interfaces`` and ``app`` may both import ``core``. Reaching a *plugin* is
``app``'s job, and ``interfaces`` does it in four places anyway — the vector
store, the Obsidian writer, the Unpaywall record fetch and the connector
registry — because the MCP tools build those adapters themselves instead of
taking them from the composition root. Those four are named and frozen in
``tests/test_architecture.py``; the pure helpers that used to travel the same
road live in ``core`` now, so the list cannot grow by accident.
"""

from .main import AcademicHunter

__all__ = ['AcademicHunter']
