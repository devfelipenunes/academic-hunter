"""Per-domain pacing must hold when connector threads run concurrently.

The delay exists to keep the pipeline inside each API's rate limit. Reading the
last-request time under the lock, sleeping outside it and recording afterwards
lets two threads compute the same wait and fire together — the limit is exceeded
by exactly the concurrency the pacing was added for.
"""

import threading
import time

from academic_hunter.plugins.connectors.base import BaseConnector

DELAY = 0.15
DOMAIN = "example.org"


def make_connector():
    connector = BaseConnector(
        cache=None,
        settings={},
        query_history=[],
        lock=threading.RLock(),
        semaphore=threading.Semaphore(8),
        use_cache=False,
    )
    connector.pacing_delays = {DOMAIN: DELAY}
    return connector


def fire(connector, count=4):
    """Run ``count`` threads through the pacing gate and return their times."""
    times = []
    times_lock = threading.Lock()
    start = threading.Barrier(count)

    def worker():
        start.wait()  # release them together, so the race is real
        connector._apply_pacing(DOMAIN)
        with times_lock:
            times.append(time.monotonic())

    threads = [threading.Thread(target=worker) for _ in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return sorted(times)


def test_concurrent_callers_are_spaced_by_the_delay():
    connector = make_connector()

    times = fire(connector)

    gaps = [b - a for a, b in zip(times, times[1:])]
    assert all(gap >= DELAY * 0.8 for gap in gaps), (
        f"callers were not paced apart: gaps={[round(g, 3) for g in gaps]}"
    )


def test_the_first_caller_does_not_wait():
    connector = make_connector()

    started = time.monotonic()
    connector._apply_pacing(DOMAIN)

    assert time.monotonic() - started < DELAY / 2


def test_the_slot_is_claimed_before_sleeping():
    """What the map holds is the intended firing time, not the last one."""
    connector = make_connector()
    before = time.monotonic()

    connector._apply_pacing(DOMAIN)

    assert connector.last_request_by_domain[DOMAIN] >= before
