"""The User-Agent carries the package version, never a literal that drifts.

Measured defect: every connector advertised `AcademicHunter/2.0.0` while the
package had moved on to 2.1.0, and the citation probe carried a second literal
(`academic-hunter/2.1`). This header is the only version most upstream APIs
ever see — arXiv, Crossref, OpenAlex, Semantic Scholar, DOAJ, DBLP, CORE — so a
stale literal is the one they believe.
"""

import pathlib
import re
import threading

from academic_hunter import __version__
from academic_hunter.plugins.connectors.base import BaseConnector

SRC = pathlib.Path(__file__).resolve().parent.parent.parent / "src"

#: `AcademicHunter/2.0.0`, `academic-hunter/2.1` — a version glued to the name.
#: The MCP resource URI `academic-hunter://papers/{doi}` has no digit there and
#: is deliberately out of reach.
_VERSIONED_AGENT = re.compile(r"academic[-_]?hunter/\d", re.IGNORECASE)


def _connector(settings=None):
    return BaseConnector(
        cache=None,
        settings=settings or {},
        query_history=None,
        lock=threading.Lock(),
        semaphore=threading.Semaphore(1),
    )


def test_the_connector_user_agent_carries_the_package_version():
    assert f"AcademicHunter/{__version__}" in _connector().get_headers()["User-Agent"]


def test_the_connector_user_agent_still_carries_the_contact_address():
    """Unpaywall and Crossref ban clients with no address; the fallback keeps one."""

    headers = _connector({"user_email": "someone@example.org"}).get_headers()
    assert "mailto:someone@example.org" in headers["User-Agent"]


def test_no_module_hardcodes_a_version_into_a_user_agent():
    offenders = [
        f"{path.relative_to(SRC)}:{number}"
        for path in SRC.rglob("*.py")
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if _VERSIONED_AGENT.search(line)
    ]
    assert not offenders, f"hardcoded version in a User-Agent: {offenders}"
