"""Which connector owns a host, and therefore whose credentials a request carries."""

from typing import Any, Dict

from ..core.infra.transport import host_of


class HunterRoutingMixin:
    """One of the parts ``AcademicHunter`` is assembled from."""

    def _make_request(self, url: str, params: Dict[str, Any] = None, timeout: int = 20, max_retries: int = 2) -> Any:
        """Send a request through the connector that owns the URL's host.

        Raises:
            ValueError: If no configured connector owns the host. Refusing is
                the point: the alternative is borrowing another source's
                credentials.
        """
        host = host_of(url)
        for connector in self.connectors.values():
            if getattr(connector, "domain", "") == host:
                return connector._make_request(url, params, timeout, max_retries)

        raise ValueError(
            f"No connector owns host {host!r}; refusing to send the request "
            f"under another source's credentials."
        )
