import logging
import time
import requests
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

# Read from the package root rather than repeating the number: this header is
# the only version most upstream APIs ever see, and a literal here drifts
# silently (it sat at 2.0.0 while the package was 2.1.0).
from academic_hunter import __version__

logger = logging.getLogger("academic_hunter.connectors")

#: First wait before retrying a transient failure; doubles per attempt.
#: A 404 does not become a 200 by waiting, and 429 has its own escalation.
_RETRY_BACKOFF_SECONDS = 0.5


class BaseConnector:
    """Base API connector handling domain pacing, concurrency limits, retries, and caching."""
    fetch_suffix = ""
    is_keyword_only = False
    domain = ""
    default_delay = 1.5
    resolve_priority = 0
    #: Stamped on every paper and used as the key in `stats["identified"]`; it
    #: has to match the name the connector is registered under.
    SOURCE_NAME = ""

    def __init__(self, cache, settings, query_history, lock, semaphore, use_cache=True):
        self.cache = cache
        self.settings = settings
        self.query_history = query_history
        self.lock = lock
        self.semaphore = semaphore
        self.use_cache = use_cache

        # Shared mutable state — overwritten by the engine after construction
        self.pacing_delays: Dict[str, float] = {}
        self.last_request_by_domain: Dict[str, float] = {}
        self.blocked_sources: set = set()

    def setup_pacing(self):
        """Optional hook for connectors to dynamically adjust their pacing delays."""
        pass

    def get_headers(self) -> Dict[str, str]:
        """Returns HTTP headers for this connector. Override in subclasses to add API keys."""
        email = self.settings.get('user_email', 'academic_hunter@example.com')
        return {
            "User-Agent": f"AcademicHunter/{__version__} (mailto:{email})"
        }

    def resolve_abstract_by_doi(self, doi: str) -> str:
        """Resolves the abstract for a given DOI. Connector plugins can optionally implement this."""
        return ""

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

        # The sleep stays outside the lock so it does not block other domains.
        if wait_time > 0:
            time.sleep(wait_time)

    def _raw_request(self, url: str, params: Dict[str, Any] = None, timeout: int = 20, max_retries: int = 2) -> Optional[requests.Response]:
        """
        Low-level HTTP GET with pacing, retries, rate-limit escalation, and concurrency control.
        Returns the raw Response object (or None on failure).
        Use this for non-JSON responses (e.g. ArXiv XML).
        """
        domain = url.split('/')[2]

        with self.lock:
            if domain in self.blocked_sources:
                return None

        headers = self.get_headers()

        for attempt in range(max_retries):
            self._apply_pacing(domain)

            with self.semaphore:
                try:
                    resp = requests.get(url, params=params, headers=headers, timeout=timeout)
                    if resp.status_code == 429:
                        retry_after_sec = 30  # default backoff if no header is present
                        
                        # 1. Standard Retry-After header (ex: OpenAlex)
                        if 'Retry-After' in resp.headers:
                            try:
                                retry_after_sec = int(resp.headers['Retry-After'])
                            except ValueError:
                                pass
                        
                        # 2. Custom header like X-Ratelimit-Retry-After (ex: CORE)
                        elif 'X-Ratelimit-Retry-After' in resp.headers:
                            try:
                                ts_str = resp.headers['X-Ratelimit-Retry-After']
                                dt_target = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                                dt_now = datetime.now(timezone.utc)
                                diff = (dt_target - dt_now).total_seconds()
                                if diff > 0:
                                    retry_after_sec = int(diff) + 1
                            except Exception:
                                pass
                                
                        # Safety lock: if wait is >60s, block source to avoid halting the engine
                        if retry_after_sec > 60:
                            logger.error(f"HTTP 429 from {domain}. API requested wait of {retry_after_sec}s. Too long! Blocking source immediately.")
                            with self.lock:
                                self.blocked_sources.add(domain)
                            return None
                        
                        if attempt < max_retries - 1:
                            with self.lock:
                                old_delay = self.pacing_delays.get(domain, self.default_delay)
                                new_delay = old_delay * 2.0
                                self.pacing_delays[domain] = new_delay
                                logger.warning(f"HTTP 429 from {domain}. Waiting {retry_after_sec}s. Escalating pacing: {old_delay}s -> {new_delay}s.")
                            time.sleep(retry_after_sec)
                            continue
                        else:
                            logger.error(f"HTTP 429 from {domain}. Max retries exceeded. Blocking source.")
                            with self.lock:
                                self.blocked_sources.add(domain)
                            return None

                    if resp.status_code != 200:
                        # A 5xx is the server saying "not now"; retrying it with
                        # no wait spends the budget without the pause it asked for.
                        if resp.status_code >= 500:
                            self._backoff(domain, attempt, max_retries)
                        continue

                    return resp
                except Exception as e:
                    logger.debug(f"Request to {domain} failed (attempt {attempt + 1}): {e}")
                    self._backoff(domain, attempt, max_retries)
                    continue
        return None

    def _backoff(self, domain: str, attempt: int, max_retries: int) -> None:
        """Wait before the next attempt, unless this was the last one.

        Pacing spaces different queries apart; this spaces the retries of one
        failing request, which nothing else covers.
        """
        if attempt >= max_retries - 1:
            return
        wait = _RETRY_BACKOFF_SECONDS * (2 ** attempt)
        logger.debug("Retrying %s in %.1fs (attempt %d).", domain, wait, attempt + 1)
        time.sleep(wait)

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
                except Exception:
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
