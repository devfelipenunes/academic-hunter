"""Retries must wait between attempts.

Measured defect: only HTTP 429 had a wait. A 5xx, or a connection that dropped,
went straight back out — the retry budget was spent in the same instant the
server said "not now", which is not a retry, it is the same request twice.
"""

import threading
from unittest.mock import MagicMock, patch

import pytest

from academic_hunter.plugins.connectors.base import BaseConnector

URL = "https://example.org/search"


def make_connector():
    connector = BaseConnector(
        cache=None,
        settings={},
        query_history=[],
        lock=threading.RLock(),
        semaphore=threading.Semaphore(8),
        use_cache=False,
    )
    connector.pacing_delays = {"example.org": 0.0}
    connector.default_delay = 0.0
    return connector


def response(status):
    resp = MagicMock()
    resp.status_code = status
    return resp


def attempt_with(connector, outcomes, max_retries=3):
    """Run one request, capturing every sleep instead of taking it."""
    if not isinstance(outcomes, list):
        # The same outcome every time: mock's `side_effect` needs a sequence.
        outcomes = [outcomes] * max_retries
    with patch("academic_hunter.plugins.connectors.base.requests.get") as get, patch(
        "academic_hunter.plugins.connectors.base.time.sleep"
    ) as sleep:
        get.side_effect = outcomes
        result = connector._raw_request(URL, max_retries=max_retries)
    return result, [call.args[0] for call in sleep.call_args_list]


def test_a_5xx_waits_before_the_next_attempt():
    connector = make_connector()

    _, waits = attempt_with(connector, [response(503)] * 3)

    assert waits, "a 5xx was retried with no wait at all"
    assert waits[0] > 0


def test_a_dropped_connection_waits_too():
    connector = make_connector()

    _, waits = attempt_with(connector, ConnectionError("connection reset"))

    assert waits, "a network failure was retried with no wait at all"


def test_the_wait_grows_with_each_attempt():
    connector = make_connector()

    _, waits = attempt_with(connector, [response(500)] * 3, max_retries=3)

    assert waits == sorted(waits) and waits[0] < waits[1], (
        f"the backoff is not exponential: {waits}"
    )


def test_nothing_is_waited_after_the_last_attempt():
    """Sleeping then giving up only delays the failure."""
    connector = make_connector()

    result, waits = attempt_with(connector, [response(500)] * 3, max_retries=3)

    assert result is None
    assert len(waits) == 2, f"waited after the final attempt: {waits}"


def test_a_client_error_is_not_waited_on():
    """A 404 does not become a 200 by waiting."""
    connector = make_connector()

    _, waits = attempt_with(connector, response(404))

    assert waits == []


def test_a_200_returns_without_waiting():
    connector = make_connector()

    result, waits = attempt_with(connector, response(200))

    assert result is not None
    assert waits == []


def test_a_success_after_a_failure_still_returns():
    connector = make_connector()

    result, waits = attempt_with(connector, [response(500), response(200)])

    assert result is not None
    assert waits, "the retry did not wait"
