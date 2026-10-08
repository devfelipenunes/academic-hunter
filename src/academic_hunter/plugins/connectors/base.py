import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from academic_hunter import __version__

logger = logging.getLogger("academic_hunter.connectors")

_RETRY_BACKOFF_SECONDS = 0.5


KEYWORD_QUERY_MAX_TERMS = 5


def _distinct(terms: List[str]) -> List[str]:
    """The terms, in order, without repeats — case-insensitively."""
    seen: Dict[str, str] = {}
    for term in terms:
        text = str(term).strip()
        if text:
            seen.setdefault(text.lower(), text)
    return list(seen.values())


def keyword_terms(
    anchors: List[str],
    tech_strings: List[str],
    max_terms: int = KEYWORD_QUERY_MAX_TERMS,
) -> List[str]:
    """Which terms a keyword-only source should search for — not how to join them.

    The selection, separated from the syntax, because the sources disagree about
    the syntax and agree about the terms. Measured on the same four Stellar
    anchors, against the live APIs:

        Semantic Scholar    the phrases as written        51 results
                            them quoted and OR-joined      0
        DOAJ                quoted and OR-joined          21
                            the phrases as written         0

    One helper that also joined them could only ever be right for one of the two.

    The anchors carry the search and the fallback terms do not join them, because
    on these endpoints a fallback term narrows rather than broadens: one added to
    the Stellar anchors took 51 results down to 6, reproducibly. So
    `keyword_only_terms` does what its name says — it is the fallback for a topic
    configured with no anchors at all.

    The three connectors this replaced joined `anchors[:3]` and `tech_strings[:2]`
    silently, so an operator configuring four anchors got three and no way to
    find out. The bound is still here, and anything it drops is named in the log.
    """
    selected = _distinct(anchors)
    if not selected:
        selected = _distinct(tech_strings)

    if len(selected) > max_terms:
        logger.warning(
            "Keyword-only query keeps %d of %d configured terms; dropped: %s. "
            "A longer query is not a broader one on these sources.",
            max_terms, len(selected), ", ".join(selected[max_terms:]),
        )
        selected = selected[:max_terms]
    return selected


def quoted_ors(terms: List[str]) -> str:
    """`"a" OR "b"` — the query syntax DOAJ and CORE's field prefixes expect."""
    return " OR ".join(f'"{term}"' for term in terms)


class BaseConnector:
    """Base API connector handling domain pacing, concurrency limits, retries, and caching."""
    fetch_suffix = ""
    is_keyword_only = False
    domain = ""
    default_delay = 1.5
    resolve_priority = 0
    SOURCE_NAME = ""

    def __init__(self, cache, settings, query_history, lock, semaphore, use_cache=True):
        self.cache = cache
        self.settings = settings
        self.query_history = query_history
        self.lock = lock
        self.semaphore = semaphore
        self.use_cache = use_cache

        self.pacing_delays: Dict[str, float] = {}
        self.last_request_by_domain: Dict[str, float] = {}
        self.blocked_sources: set = set()

    def setup_pacing(self):
        """Optional hook for connectors to dynamically adjust their pacing delays."""
        pass

    @classmethod
    def unavailable_reason(cls, settings) -> str:
        """Why this connector cannot run with ``settings``, or ``""`` when it can.

        Evaluated once per run rather than at construction: a credential can be
        configured between two runs, and the answer has to follow it.

        A connector that returns a reason is left out of the run and named in
        the reply. Calling it anyway is the worse option for a source that needs
        a credential -- it gets throttled into a blocked source partway through
        and reports a zero nobody can tell from a source that was asked and
        found nothing.
        """
        return ""

    def get_headers(self) -> Dict[str, str]:
        """Returns HTTP headers for this connector. Override in subclasses to add API keys."""
        email = self.settings.get('user_email', 'academic_hunter@example.com')
        return {
            "User-Agent": f"AcademicHunter/{__version__} (mailto:{email})"
        }

    def resolve_metadata_by_doi(self, doi: str) -> Dict[str, Any]:
        """What this source knows about a DOI, keyed by field name.

        ``Abstract``, ``Authors`` and ``Citations`` are the keys a resolver may
        return, and a source returns only the ones it actually has — an absent
        key means "not known here", never zero. The default is empty: a source
        with no DOI-addressed lookup at all is skipped rather than asked.
        """
        return {}

    def resolve_abstract_by_doi(self, doi: str) -> str:
        """Resolves the abstract for a given DOI. Connector plugins can optionally implement this."""
        return str(self.resolve_metadata_by_doi(doi).get("Abstract") or "")

    def detect_peer_review(self, doc_type: str) -> str:
        """Determines if a document is peer reviewed based on its type/venue. Override in subclasses."""
        return "N/A"

    def _apply_pacing(self, domain: str) -> None:
        """Waits the required pacing delay for a domain (thread-safe).

        The slot is claimed *before* sleeping — the map holds the instant this
        thread intends to fire, not the one it last fired at. Reading the
        timestamp under the lock, sleeping outside it and writing afterwards let
        two threads compute the same wait and issue simultaneously, which is
        exactly what the per-domain delay exists to prevent.
        """
        with self.lock:
            delay = self.pacing_delays.get(domain, self.default_delay)
            now = time.time()
            wait_time = max(0.0, delay - (now - self.last_request_by_domain.get(domain, 0.0)))
            self.last_request_by_domain[domain] = now + wait_time

        if wait_time > 0:
            time.sleep(wait_time)

    def _raw_request(self, url: str, params: Dict[str, Any] = None, timeout: int = 20, max_retries: int = 2) -> Optional[requests.Response]:
        """
        Low-level HTTP GET with pacing, retries, rate-limit escalation, and concurrency control.
        Returns the raw Response object (or None on failure).
        Use this for non-JSON responses (e.g. ArXiv XML).

        Every wait happens *outside* the concurrency semaphore. The semaphore is
        shared by all connectors and has two slots, so a 30-second rate-limit
        wait taken inside it stopped the other sources from fetching too: one
        throttled API stalled the whole run, which is the opposite of what a
        per-source backoff is for. ``_apply_pacing`` already separates deciding
        the wait from taking it, for the same reason.
        """
        domain = url.split('/')[2]

        with self.lock:
            if domain in self.blocked_sources:
                return None

        headers = self.get_headers()

        for attempt in range(max_retries):
            self._apply_pacing(domain)
            wait = 0.0

            with self.semaphore:
                try:
                    resp = requests.get(url, params=params, headers=headers, timeout=timeout)
                    if resp.status_code == 429:
                        wait = self._note_rate_limit(domain, resp, attempt, max_retries)
                        if wait is None:
                            return None
                    elif resp.status_code != 200:
                        if resp.status_code >= 500:
                            wait = self._backoff(domain, attempt, max_retries)
                        else:
                            continue
                    else:
                        return resp
                except Exception as e:
                    logger.debug(f"Request to {domain} failed (attempt {attempt + 1}): {e}")
                    wait = self._backoff(domain, attempt, max_retries)

            if wait:
                time.sleep(wait)
        return None

    def _note_rate_limit(self, domain: str, response: requests.Response, attempt: int, max_retries: int) -> Optional[float]:
        """How long to wait after a 429, or ``None`` when the source must be blocked.

        Split out of the request loop so the caller can leave the semaphore
        before taking the wait; see ``_raw_request``.
        """
        retry_after_sec = 30

        if 'Retry-After' in response.headers:
            try:
                retry_after_sec = int(response.headers['Retry-After'])
            except ValueError:
                pass

        elif 'X-Ratelimit-Retry-After' in response.headers:
            try:
                ts_str = response.headers['X-Ratelimit-Retry-After']
                dt_target = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                dt_now = datetime.now(timezone.utc)
                diff = (dt_target - dt_now).total_seconds()
                if diff > 0:
                    retry_after_sec = int(diff) + 1
            except Exception:  # noqa: S110
                pass

        if retry_after_sec > 60:
            logger.error(f"HTTP 429 from {domain}. API requested wait of {retry_after_sec}s. Too long! Blocking source immediately.")
            with self.lock:
                self.blocked_sources.add(domain)
            return None

        if attempt >= max_retries - 1:
            logger.error(f"HTTP 429 from {domain}. Max retries exceeded. Blocking source.")
            with self.lock:
                self.blocked_sources.add(domain)
            return None

        with self.lock:
            old_delay = self.pacing_delays.get(domain, self.default_delay)
            new_delay = old_delay * 2.0
            self.pacing_delays[domain] = new_delay
            logger.warning(f"HTTP 429 from {domain}. Waiting {retry_after_sec}s. Escalating pacing: {old_delay}s -> {new_delay}s.")
        return retry_after_sec

    def _backoff(self, domain: str, attempt: int, max_retries: int) -> float:
        """How long to wait before the next attempt, or 0 on the last one.

        Pacing spaces different queries apart; this spaces the retries of one
        failing request, which nothing else covers. The caller takes the wait —
        see ``_raw_request``.
        """
        if attempt >= max_retries - 1:
            return 0.0
        wait = _RETRY_BACKOFF_SECONDS * (2 ** attempt)
        logger.debug("Retrying %s in %.1fs (attempt %d).", domain, wait, attempt + 1)
        return wait

    def _make_request(self, url: str, params: Dict[str, Any] = None, timeout: int = 20, max_retries: int = 2) -> Any:
        """
        High-level HTTP GET that returns parsed JSON, with caching support.
        Use _raw_request() for non-JSON responses.
        """
        param_str = json.dumps(params, sort_keys=True) if params else ""
        cache_key = f"{url}?{param_str}"

        if self.use_cache and self.cache:
            cached_val = self.cache.get(cache_key)
            if cached_val:
                try:
                    return json.loads(cached_val)
                except Exception:  # noqa: S110
                    pass

        resp = self._raw_request(url, params, timeout, max_retries)
        if resp is None:
            return None

        try:
            res_json = resp.json()
            if self.use_cache and self.cache:
                self.cache.set(cache_key, json.dumps(res_json))
            return res_json
        except Exception:
            return None

    def fetch(self, anchors: List[str], tech_strings: List[str], limit: int = 50) -> List[Dict[str, Any]]:
        raise NotImplementedError("Each connector plugin must implement 'fetch' method.")
