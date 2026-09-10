"""On-disk cache for downloaded PDFs.

Keyed by URL, which is the only identifier :meth:`FullTextSourcePort.download`
receives. Wrapping the source instead of teaching the step about caching is what
makes "a second run does not hit the network" a property of the wiring.
"""

import hashlib
import logging
from pathlib import Path
from typing import Optional

from ...core.ports.fulltext import FullTextTransientError, OpenAccessLocation

logger = logging.getLogger("academic_hunter.fulltext.cache")


class PdfCache:
    """PDF bytes on disk, under a directory of their own."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def path_for(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
        return self.root / f"{digest}.pdf"

    def get(self, url: str) -> Optional[bytes]:
        """The cached PDF, or None. A damaged cache entry is treated as absent."""
        path = self.path_for(url)
        if not path.exists():
            return None
        try:
            return path.read_bytes()
        except OSError as e:
            logger.warning("Could not read cached PDF %s: %s", path, e)
            return None

    def put(self, url: str, pdf_bytes: bytes) -> None:
        """Store the PDF, atomically so a concurrent reader never sees a partial file."""
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path_for(url)
        temporary = path.with_suffix(".part")
        try:
            temporary.write_bytes(pdf_bytes)
            temporary.replace(path)
        except OSError as e:
            logger.warning("Could not cache PDF %s: %s", path, e)
            temporary.unlink(missing_ok=True)


class CachedFullTextSource:
    """Wraps a :class:`FullTextSourcePort` so a repeat download is free.

    Only ``download`` is cached; ``locate`` still asks the network, because
    knowing whether an OA copy exists is cheap and can change between runs.
    """

    def __init__(self, source, cache: PdfCache) -> None:
        self.source = source
        self.cache = cache

    def locate(self, doi: str) -> OpenAccessLocation:
        return self.source.locate(doi)

    def download(
        self, location: OpenAccessLocation, max_bytes: int = 40_000_000
    ) -> bytes:
        cached = self.cache.get(location.url)
        if cached is not None:
            logger.debug("Full text served from cache: %s", location.url)
            return cached

        try:
            pdf_bytes = self.source.download(location, max_bytes=max_bytes)
        except FullTextTransientError:
            raise
        except Exception as e:
            raise FullTextTransientError(f"Download failed for {location.url}: {e}") from e

        self.cache.put(location.url, pdf_bytes)
        return pdf_bytes
