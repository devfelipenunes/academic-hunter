"""The transport's contract, in the parts the connector tests do not reach.

`tests/plugins/test_connector_pacing.py` and `test_connector_retry.py` fix the
mechanics through a connector, and they are the reason this extraction is
trustworthy. What they cannot say is anything about the two callers differing —
they only ever exercise the one that blocks — nor that `core` stayed free of the
HTTP library that would have to move if the policy needed `requests`.
"""

import ast
import sys
import threading
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from academic_hunter.core.infra.transport import HttpTransport

DOMAIN = "api.example.org"


def transport(**overrides) -> HttpTransport:
    base = {
        "lock": threading.Lock(),
        "pacing_delays": {},
        "last_request_by_domain": {},
        "blocked_sources": set(),
        "semaphore": threading.Semaphore(2),
        "default_delay": 0.0,
        "block_sources": False,
        "sleep": lambda seconds: None,
    }
    return HttpTransport(**{**base, **overrides})


def response(status=200, headers=None):
    mock = MagicMock()
    mock.status_code = status
    mock.headers = headers or {}
    return mock


def test_a_response_is_ok_only_when_it_is_a_200():
    """``ok`` is the transport's answer to "is there a body to read".

    A 404 and a 500 both leave ``response`` filled — the caller that raises needs
    it — but neither is a body, and a caller that treated them as one would read
    an error page as data.
    """
    for status in (200, 404, 500):
        attempt = transport().perform(lambda: response(status), domain=DOMAIN, max_retries=1)

        assert attempt.ok is (status == 200)
        assert attempt.response.status_code == status


def test_a_blocking_policy_records_the_block_and_a_non_blocking_one_does_not():
    """The switch that lets a run carry on and a one-shot call complain."""
    blocked = set()
    blocking = transport(blocked_sources=blocked, block_sources=True)
    throttled = response(429, {"Retry-After": str(24 * 3600)})

    blocking.perform(lambda: throttled, domain=DOMAIN, max_retries=3)

    assert blocked == {DOMAIN}

    quiet = set()
    tolerant = transport(blocked_sources=quiet, block_sources=False)
    tolerant.perform(lambda: throttled, domain=DOMAIN, max_retries=3)

    assert quiet == set()


def test_a_blocked_domain_is_not_called_at_all():
    calls = []
    subject = transport(blocked_sources={DOMAIN}, block_sources=True)

    attempt = subject.perform(lambda: calls.append(1), domain=DOMAIN)

    assert calls == []
    assert attempt.ok is False
    assert attempt.response is None


def test_a_rate_limit_escalates_the_delay_for_that_domain():
    delays = {}
    subject = transport(pacing_delays=delays, default_delay=2.0)

    subject.note_rate_limit(DOMAIN, response(429, {"Retry-After": "3"}), 0, 3)

    assert delays[DOMAIN] == 4.0


def test_the_iso_retry_header_is_read_too():
    """`Retry-After` is not the only shape OpenAlex uses to say when to come back."""
    later = datetime.now(timezone.utc) + timedelta(seconds=5)
    headers = {"X-Ratelimit-Retry-After": later.isoformat().replace("+00:00", "Z")}

    wait = transport().note_rate_limit(DOMAIN, response(429, headers), 0, 3)

    assert 4 <= wait <= 6


def test_http_date_retry_after_is_read():
    later = datetime.now(timezone.utc) + timedelta(seconds=5)
    headers = {"Retry-After": format_datetime(later, usegmt=True)}

    wait = transport().note_rate_limit(DOMAIN, response(429, headers), 0, 3)

    assert 4 <= wait <= 6


def test_core_infra_imports_nothing_from_outside_the_standard_library():
    """The reason the policy can live in ``core`` at all.

    `requests` is what it would reach for first, and the moment it does, the MCP
    tools cannot use it: `interfaces` may not import from `plugins`, and the
    package that owns the HTTP client is there. Measured by AST rather than by
    importing, because an import that only happens under a branch would pass.
    """
    infra = Path(__file__).resolve().parents[2] / "src" / "academic_hunter" / "core" / "infra"
    outside = set()

    for path in sorted(infra.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                outside |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                outside.add(node.module.split(".")[0])

    third_party = sorted(
        name for name in outside if name not in sys.stdlib_module_names and name != "academic_hunter"
    )

    assert not third_party, f"core/infra reaches outside the standard library: {third_party}"


def test_the_sleep_can_be_injected_without_patching_the_time_module():
    """A test that needs no waiting should not have to reach into `time`."""
    slept = []

    with patch("academic_hunter.core.infra.transport.time.sleep") as real_sleep:
        subject = transport(sleep=slept.append)
        subject.backoff = lambda domain, attempt, max_retries: 0.0
        subject.perform(lambda: response(500), domain=DOMAIN, max_retries=2)

    assert not real_sleep.called
