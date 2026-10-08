"""MCP server health check — shared logic for stdio and SSE modes."""

import importlib.metadata
import importlib.util
import json
import logging
import sys
from pathlib import Path

from academic_hunter.core.infra import paths
from mcp.server.fastmcp import Context

logger = logging.getLogger("academic_hunter.mcp")

try:
    from .tools._utils import _get_vector_store
except Exception:
    _get_vector_store = None


EXTRA_MODULES = {
    "fulltext": ("pypdf",),
    "ml": ("sentence_transformers", "sklearn", "umap", "bertopic", "hdbscan"),
}


def _module_available(name: str) -> bool:
    """Whether a module can be imported, without importing it.

    ``find_spec`` rather than ``import``: the ``ml`` extra is torch, and probing
    it by importing would spend hundreds of megabytes and seconds of the server's
    startup on a status call.
    """
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _extras_report() -> dict:
    """Which optional extras this interpreter can actually use."""
    report = {}
    for extra, modules in EXTRA_MODULES.items():
        missing = [name for name in modules if not _module_available(name)]
        report[extra] = {"available": not missing, "missing": missing}
    return report


def _identity() -> dict:
    """Which code is running, and where it came from.

    A wheel in ``dist/`` and this checkout are indistinguishable from the outside
    until something behaves differently: the same distribution version, the same
    config resolution, the same tool list. A server launched from a stale wheel
    answered every call for eleven days while the checkout's fixes sat on disk
    unread, and nothing in any reply said so.

    ``checkout_root`` is the discriminator: it walks up for a ``pyproject.toml``,
    which a wheel in site-packages does not have.
    """
    try:
        version = importlib.metadata.version("academic-hunter")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"

    package_dir = ""
    try:
        import academic_hunter

        package_dir = str(Path(academic_hunter.__file__).resolve().parent)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not locate the installed package: %s", exc)

    checkout = paths.checkout_root()

    return {
        "version": version,
        "python": sys.executable,
        "package_dir": package_dir,
        "source": "checkout" if checkout else "installed",
        "checkout_root": str(checkout) if checkout else None,
        "extras": _extras_report(),
    }


async def _check_components() -> dict:
    """Check all components and return status data.

    Off the event loop: every check below opens a file or a client, and this runs
    on the same loop as every tool — `GET /health` is what an orchestrator polls,
    so blocking here stops the server answering anything else.
    """
    from .tools._utils import run_blocking

    return await run_blocking(_probe_components)


def _probe_components() -> dict:
    """The synchronous work behind ``_check_components``.

    Returns a dict with ``status`` (ok/degraded/error), ``config_loaded``,
    ``vector_store`` info, and ``last_config_backup``.
    """
    status = "ok"
    config_loaded = True
    vector_store_available = True
    paper_count = 0
    collection = ""
    last_backup = None

    try:
        from academic_hunter.core import get_config

        get_config()
    except Exception as exc:
        config_loaded = False
        status = "degraded"
        logger.warning("Config not available: %s", exc)

    if _get_vector_store is None:
        vector_store_available = False
        if status == "ok":
            status = "degraded"
        elif not config_loaded:
            status = "error"
        logger.warning("_get_vector_store import failed")
    else:
        try:
            store = _get_vector_store()
            if store is not None:
                stats = store.collection_stats()
                if stats.get("error"):
                    raise RuntimeError(str(stats["error"]))
                paper_count = stats.get("count", 0)
                collection = str(stats.get("name") or "")
            else:
                raise RuntimeError("Vector store returned None")
        except Exception as exc:
            vector_store_available = False
            if status == "ok":
                status = "degraded"
            elif not config_loaded:
                status = "error"
            logger.warning("Vector store not available: %s", exc)

    try:
        from .memory.config_backup import MCPDatabaseManager

        db = MCPDatabaseManager()
        history = db.list_configs(limit=1)
        if history:
            last_backup = history[0].get("timestamp")
    except Exception:  # noqa: S110
        pass

    return {
        "status": status,
        "server": "academic-hunter",
        "identity": _identity(),
        "config_loaded": config_loaded,
        "paths": paths.describe(),
        "vector_store": {
            "available": vector_store_available,
            "collection": collection,
            "paper_count": paper_count,
        },
        "last_config_backup": last_backup,
    }


async def server_status(ctx: Context) -> str:
    """Returns diagnostic information about the MCP server and its dependencies.

    Checks:
    - Which code is running? ``identity`` reports the version, the interpreter,
      the directory the package was imported from, whether that is this checkout
      or an installed copy, and which optional extras are importable. A server
      launched from a stale wheel and a server running the checkout answer
      identically in every other field, so this is the only way to tell them
      apart -- and a missing extra is why an analysis tool fails rather than
      returning nothing.
    - Can configuration be loaded?
    - Is the vector store (ChromaDB) available? ``vector_store.collection``
      names the collection the configuration points at, and the count is that
      collection's — one collection per review, so this is how many papers this
      review has rather than how many every review ever run put there.
    - When was the last config backup?

    Returns a JSON string with the overall ``status`` (ok / degraded / error)
    and per-component detail.
    """
    await ctx.info("Checking server status...")
    data = await _check_components()
    await ctx.info(f"Server status: {data['status']}")
    return json.dumps(data, ensure_ascii=False)
