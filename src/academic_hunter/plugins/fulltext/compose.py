"""Composing the full-text sources into one callable: DOI in, document out.

Lives below ``app/`` so the MCP tool and the evaluation script can get the same
chain without standing up a whole hunter.
"""

import logging
from pathlib import Path

from ...core.ports.fulltext import FullTextConfigError
from .cache import CachedFullTextSource, PdfCache
from .europepmc import EuropePmcSource
from .pdf import PdfExtractor
from .sources import ChainFullTextSource, UnpaywallPdfSource
from .unpaywall import UnpaywallSource

logger = logging.getLogger("academic_hunter.fulltext.compose")


def build_full_text_fetcher(email: str, cache_dir: Path) -> ChainFullTextSource:
    """Unpaywall first — it is the index of where open copies live — Europe PMC after.

    An unusable e-mail drops the Unpaywall leg rather than the whole feature:
    Europe PMC needs no address.
    """
    sources = [EuropePmcSource()]

    try:
        pdf_source = CachedFullTextSource(
            UnpaywallSource(email),
            PdfCache(Path(cache_dir)),
        )
    except FullTextConfigError as e:
        logger.info("Unpaywall unavailable (%s); using Europe PMC only.", e)
    else:
        sources.insert(0, UnpaywallPdfSource(pdf_source, PdfExtractor()))

    return ChainFullTextSource(sources)
