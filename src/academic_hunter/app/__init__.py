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
Both ``interfaces`` and ``app`` may import ``core``; only ``app`` imports
``plugins``.
"""

from .main import AcademicHunter

__all__ = ['AcademicHunter']
