from .arxiv import ArxivConnector
from .crossref import CrossrefConnector
from .openalex import OpenAlexConnector
from .semanticscholar import SemanticScholarConnector
from .core_ac import CoreConnector
from .dblp import DblpConnector
from .doaj import DoajConnector

CONNECTORS = {
    "ArXiv": ArxivConnector,
    "Crossref": CrossrefConnector,
    "OpenAlex": OpenAlexConnector,
    "Semantic Scholar": SemanticScholarConnector,
    "CORE": CoreConnector,
    "DBLP": DblpConnector,
    "DOAJ": DoajConnector
}
