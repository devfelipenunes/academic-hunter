"""Pacing and retry for one API, in one place for every caller that has one.

Two clients spoke to OpenAlex with two policies. The pipeline spaced its
requests by domain, doubled the delay on a 429, retried a 5xx and a dropped
connection, and identified itself in a ``User-Agent``; the MCP tools spaced
theirs by a fixed half-second, retried nothing but a 429, and sent no
``User-Agent`` at all. A fix to either reached the other never.

What is shared is the policy: how long to wait, when to give up, what to send.
What is not shared is the client — this module never imports `requests`, so the
caller brings the request as a callable and keeps its own HTTP library, its own
query building and its own idea of what the response means. That is also what
lets this live in ``core``, which imports no third-party module.

The two callers need opposite things from a spent budget, and ``block_sources``
is the switch: the pipeline has to finish a run, so a source that will not
answer is blocked and its absence is reported as a source that was not queried;
a one-shot MCP call has to say what happened, so it exhausts its attempts and
raises with the response in hand.
"""

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Dict, Optional, Set
from urllib.parse import urlsplit

logger = logging.getLogger("academic_hunter.transport")

DEFAULT_BACKOFF_SECONDS = 0.5
RATE_LIMIT_DEFAULT_WAIT = 30
BLOCK_ABOVE_SECONDS = 60

POLITE_EMAIL_FALLBACK = "academic_hunter@example.com"


def polite_email(settings: Dict[str, Any]) -> str:
    """The address to put in a ``mailto``, always something.

    Several of these APIs run a faster pool for callers who say who they are,
    and OpenAlex's is entered with ``mailto``. The MCP tools sent one only when
    ``user_email`` was configured, so a caller who had not set one was anonymous
    while the pipeline was not.
    """
    return str(settings.get("user_email") or POLITE_EMAIL_FALLBACK)


def user_agent(email: str, version: str) -> str:
    """How this project introduces itself to an API."""
    return f"AcademicHunter/{version} (mailto:{email})"


def host_of(url: str) -> str:
    """The host a URL points at, as the connectors spell their ``domain``."""
    return urlsplit(url).netloc


@dataclass(frozen=True)
class Attempt:
    """What came of one request, after whatever retrying the policy allowed.

    ``response`` is carried even when the request failed, because the caller
    that raises needs the response to raise *from* — an exception without one
    loses the status code, and the status code is the difference between "the
    API is rate-limiting you, here is when it resets" and "something went
    wrong".
    """

    response: Any = None
    error: Optional[BaseException] = None
    ok: bool = False


class HttpTransport:
    """How one domain is asked, shared by every caller that asks it.

    Takes its state rather than owning it: the pipeline re-points
    ``pacing_delays``, ``last_request_by_domain`` and ``blocked_sources`` at the
    run's dictionaries after constructing its connectors, and clears them
    between runs, so a transport that captured them would pace against a map
    nobody reads any more.
    """

    def __init__(
        self,
        *,
        lock: threading.Lock,
        pacing_delays: Dict[str, float],
        last_request_by_domain: Dict[str, float],
        blocked_sources: Set[str],
        semaphore: Optional[threading.Semaphore] = None,
        default_delay: float = 1.5,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
        block_sources: bool = True,
        sleep: Optional[Callable[[float], None]] = None,
    ) -> None:
        self.lock = lock
        self.pacing_delays = pacing_delays
        self.last_request_by_domain = last_request_by_domain
        self.blocked_sources = blocked_sources
        self.semaphore = semaphore if semaphore is not None else threading.Semaphore(2)
        self.default_delay = default_delay
        self.backoff_seconds = backoff_seconds
        self.block_sources = block_sources
        self._sleep = sleep

    def _wait(self, seconds: float) -> None:
        """Resolved per call, so a caller can inject one without patching `time`."""
        (self._sleep or time.sleep)(seconds)

    def pace(self, domain: str) -> None:
        """Wait the delay this domain is owed.

        The slot is claimed *before* sleeping: the map holds the instant this
        caller intends to fire, not the one it last fired at. Reading the
        timestamp under the lock, sleeping outside it and writing afterwards let
        two callers compute the same wait and issue simultaneously, which is
        exactly what a per-domain delay exists to prevent.
        """
        with self.lock:
            delay = self.pacing_delays.get(domain, self.default_delay)
            now = time.time()
            wait_time = max(0.0, delay - (now - self.last_request_by_domain.get(domain, 0.0)))
            self.last_request_by_domain[domain] = now + wait_time

        if wait_time > 0:
            self._wait(wait_time)

    def backoff(self, domain: str, attempt: int, max_retries: int) -> float:
        """How long to wait before the next attempt, or 0 on the last one.

        Pacing spaces different queries apart; this spaces the retries of one
        failing request, which nothing else covers.
        """
        if attempt >= max_retries - 1:
            return 0.0
        wait = self.backoff_seconds * (2**attempt)
        logger.debug("Retrying %s in %.1fs (attempt %d).", domain, wait, attempt + 1)
        return wait

    def note_rate_limit(
        self, domain: str, response: Any, attempt: int, max_retries: int
    ) -> Optional[float]:
        """How long to wait after a 429, or ``None`` when there is no point waiting.

        ``None`` means the caller stops. Whether that also blocks the domain for
        the rest of the session is ``block_sources``: a run continues without
        the source, a one-shot call has nothing to continue with.
        """
        wait = RATE_LIMIT_DEFAULT_WAIT

        if "Retry-After" in response.headers:
            retry_after = response.headers["Retry-After"]
            try:
                wait = max(0, int(retry_after))
            except (TypeError, ValueError):
                try:
                    target = parsedate_to_datetime(retry_after)
                    if target.tzinfo is None:
                        target = target.replace(tzinfo=timezone.utc)
                    wait = max(0, int((target - datetime.now(timezone.utc)).total_seconds() + 0.999))
                except (TypeError, ValueError, OverflowError):
                    pass
        elif "X-Ratelimit-Retry-After" in response.headers:
            try:
                target = datetime.fromisoformat(
                    response.headers["X-Ratelimit-Retry-After"].replace("Z", "+00:00")
                )
                difference = (target - datetime.now(timezone.utc)).total_seconds()
                if difference > 0:
                    wait = int(difference) + 1
            except Exception:  # noqa: S110
                pass

        if wait > BLOCK_ABOVE_SECONDS:
            return self._give_up(domain, f"API requested a wait of {wait}s. Too long!")
        if attempt >= max_retries - 1:
            return self._give_up(domain, "Max retries exceeded.")

        with self.lock:
            old_delay = self.pacing_delays.get(domain, self.default_delay)
            new_delay = old_delay * 2.0
            self.pacing_delays[domain] = new_delay
        logger.warning(
            "HTTP 429 from %s. Waiting %ss. Escalating pacing: %ss -> %ss.",
            domain, wait, old_delay, new_delay,
        )
        return wait

    def _give_up(self, domain: str, reason: str) -> Optional[float]:
        """Stop, and block the domain when this policy blocks domains."""
        if not self.block_sources:
            logger.error("HTTP 429 from %s. %s Giving up on this request.", domain, reason)
            return 0.0
        logger.error("HTTP 429 from %s. %s Blocking source.", domain, reason)
        with self.lock:
            self.blocked_sources.add(domain)
        return None

    def perform(
        self, request: Callable[[], Any], *, domain: str, max_retries: int = 2
    ) -> Attempt:
        """Issue ``request`` until it answers, and report what happened.

        Every wait happens *outside* the semaphore. The semaphore is shared by
        all callers, so a thirty-second rate-limit wait taken inside it stopped
        every other source from fetching too: one throttled API stalled the whole
        run, which is the opposite of what a per-source backoff is for.
        """
        if self.block_sources and self._is_blocked(domain):
            return Attempt()

        error: Optional[BaseException] = None
        response = None

        for attempt in range(max_retries):
            self.pace(domain)
            wait = 0.0

            with self.semaphore:
                try:
                    response = request()
                    if response.status_code == 429:
                        wait = self.note_rate_limit(domain, response, attempt, max_retries)
                        if wait is None:
                            return Attempt(response=response)
                    elif response.status_code != 200:
                        if response.status_code >= 500:
                            wait = self.backoff(domain, attempt, max_retries)
                        else:
                            continue
                    else:
                        return Attempt(response=response, ok=True)
                except Exception as exc:
                    logger.debug(
                        "Request to %s failed (attempt %d): %s", domain, attempt + 1, exc
                    )
                    error = exc
                    wait = self.backoff(domain, attempt, max_retries)

            if wait:
                self._wait(wait)

        return Attempt(response=response, error=error)

    def _is_blocked(self, domain: str) -> bool:
        with self.lock:
            return domain in self.blocked_sources
