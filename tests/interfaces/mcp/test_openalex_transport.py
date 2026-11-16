"""There is one pacing-and-retry policy, and both callers are on it.

The pipeline's connectors and the MCP discovery tools used to reach OpenAlex
through two clients with two policies: half a second by a private constant on one
side, a per-domain delay that doubles on a 429 on the other, and a 429 handled
two different ways. Both now go through ``core.infra.transport``.

The test that matters most here is the first one. Asserting that the two paths
*wait the same amounts today* would pass on a second implementation that happens
to agree, and a second implementation that agrees is the thing being ruled out.
Patching the policy's own ``backoff`` and finding both paths honouring the patched
number is a claim about there being one definition, not about two behaviours
matching.
"""

import threading
from unittest.mock import MagicMock, patch

import pytest

from academic_hunter.core.infra.transport import HttpTransport
from academic_hunter.interfaces.mcp.tools import _utils
from academic_hunter.plugins.connectors.base import BaseConnector

URL = "https://api.openalex.org/works"


def response(status=200, headers=None):
    mock = MagicMock()
    mock.status_code = status
    mock.headers = headers or {}
    mock.json.return_value = {"ok": True}
    return mock


def connector():
    """A connector with no pacing of its own, so only the retry is measured."""
    subject = BaseConnector(
        cache=None, settings={}, query_history=[],
        lock=threading.Lock(), semaphore=threading.Semaphore(2), use_cache=False,
    )
    subject.default_delay = 0.0
    return subject


def mcp_transport(sleep=lambda seconds: None):
    """The MCP path's transport. ``sleep`` is injectable because one test below
    has to measure the waiting itself, and the rest must not wait at all."""
    return HttpTransport(
        lock=threading.Lock(),
        semaphore=threading.Semaphore(2),
        pacing_delays={},
        last_request_by_domain={},
        blocked_sources=set(),
        default_delay=0.0,
        block_sources=False,
        sleep=sleep,
    )


def test_one_backoff_number_serves_both_paths():
    """Patch the policy once, and both callers wait what it returns."""
    waits = []

    with patch.object(HttpTransport, "backoff", return_value=7.0), patch(
        "academic_hunter.core.infra.transport.time.sleep", waits.append
    ):
        with patch(
            "academic_hunter.plugins.connectors.base.requests.get",
            return_value=response(503),
        ):
            connector()._raw_request(URL, max_retries=2)

        with patch.object(_utils.requests, "get", return_value=response(503)), patch.object(
            _utils, "_openalex_transport", lambda: mcp_transport(sleep=None)
        ):
            with pytest.raises(Exception):
                _utils._openalex_get_sync("/works", attempts=2)

    assert waits == [7.0, 7.0, 7.0, 7.0], (
        "a caller waited something the shared policy did not return, so it has a "
        f"backoff of its own: {waits}"
    )


def test_the_mcp_module_carries_no_pacing_or_retry_of_its_own():
    """The same claim, read off the source.

    The test above proves the two agree at runtime. This one is what fails when
    somebody adds a second loop that agrees *by coincidence* — which is how the
    two implementations began.

    It names the two things a second policy cannot do without — sleeping, and
    reading the header — rather than the number 429, which is prose in this
    project as often as it is code.
    """
    import academic_hunter.interfaces.mcp.tools._utils as module

    source = open(module.__file__, encoding="utf-8").read()

    for forbidden in ("time.sleep", "Retry-After", "_OPENALEX_MIN_INTERVAL"):
        assert forbidden not in source, (
            f"_utils.py carries its own transport policy again: {forbidden!r}"
        )


def test_the_mcp_path_retries_a_5xx():
    """Behaviour it never had: it retried a 429 and nothing else.

    Only reachable by sharing the connector's policy, which is the point.
    """
    transport = mcp_transport()

    with patch.object(_utils.requests, "get") as m_get, patch.object(
        _utils, "_openalex_transport", lambda: transport
    ):
        m_get.side_effect = [response(503), response(200)]
        assert _utils._openalex_get_sync("/works") == {"ok": True}

    assert m_get.call_count == 2


def test_the_mcp_path_sends_the_polite_headers():
    """The two asymmetries the extraction was for: no User-Agent, and a mailto
    only when one had been configured."""
    from academic_hunter.core.infra.openalex import (
        openalex_headers,
        openalex_params,
    )

    headers = openalex_headers({"user_email": "someone@example.org"}, "9.9.9")
    assert headers["User-Agent"] == "AcademicHunter/9.9.9 (mailto:someone@example.org)"

    anonymous = openalex_headers({}, "9.9.9")
    assert "(mailto:academic_hunter@example.com)" in anonymous["User-Agent"]
    assert openalex_params({}) == {"mailto": "academic_hunter@example.com"}

    with patch.dict("os.environ", {"OPENALEX_API_KEY": "a-key"}):
        assert openalex_headers({}, "9.9.9")["Authorization"] == "Bearer a-key"


def test_a_spent_budget_does_not_block_the_mcp_path():
    """A one-shot call has nothing to carry on with, so it raises and says why.

    Blocking the domain instead would make the session's next call fail with no
    response at all, and the caller that builds the rate-limit message reads the
    status off the response.
    """
    import requests

    transport = mcp_transport()
    throttled = response(429, {"Retry-After": "2"})
    error = requests.HTTPError("429")
    error.response = throttled
    throttled.raise_for_status.side_effect = error

    with patch.object(_utils.requests, "get", return_value=throttled), patch.object(
        _utils, "_openalex_transport", lambda: transport
    ):
        with pytest.raises(requests.HTTPError) as raised:
            _utils._openalex_get_sync("/works", attempts=2)

    assert raised.value.response.status_code == 429
    assert transport.blocked_sources == set()
