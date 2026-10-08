from typing import Any, Dict

from .authors import normalize_authors
from .strategies import (
    strategy_anchor_category,
    strategy_authors,
    strategy_first_non_empty,
    strategy_longest_string,
    strategy_max,
    strategy_peer_reviewed,
    strategy_set_join,
    strategy_tech_category,
    strategy_url,
    strategy_venue,
    strategy_year,
)
from .utils import collapse_whitespace, normalize_doi

FIELD_SCHEMA: Dict[str, Dict[str, Any]] = {
    "Title": {
        "default": "",
        "normalize": collapse_whitespace,
    },
    "Authors": {
        "default": "",
        "normalize": normalize_authors,
        "strategy": strategy_authors
    },
    "Abstract": {
        "default": "",
        "normalize": collapse_whitespace,
        "strategy": strategy_longest_string
    },
    "Year": {
        "default": "N/A",
        "normalize": lambda x: x if x is not None else "N/A",
        "strategy": strategy_year
    },
    "URL": {
        "default": "",
        "normalize": lambda x: str(x or "").strip(),
        "strategy": strategy_url
    },
    "Source": {
        "default": "",
        "normalize": lambda x: str(x or "").strip(),
        "strategy": strategy_set_join
    },
    "Citations": {
        "default": 0,
        "normalize": lambda x: int(x or 0),
        "strategy": strategy_max
    },
    "Citations_Source": {
        "default": "",
        "normalize": lambda x: str(x or "").strip(),
        "strategy": strategy_set_join
    },
    "DOI": {
        "default": "",
        "normalize": lambda x: normalize_doi(x),
        "strategy": strategy_first_non_empty
    },
    "Peer_Reviewed": {
        "default": "N/A",
        "normalize": lambda x: str(x or "N/A").strip(),
        "strategy": strategy_peer_reviewed
    },
    "Venue": {
        "default": "Unknown Venue",
        "normalize": lambda x: str(x or "Unknown Venue").strip(),
        "strategy": strategy_venue
    },
    "Anchor_Category": {
        "default": "",
        "normalize": lambda x: str(x or "").strip(),
        "strategy": strategy_anchor_category
    },
    "Anchor_Terms": {
        "default": "",
        "normalize": lambda x: str(x or "").strip(),
        "strategy": strategy_set_join
    },
    "Tech_Category": {
        "default": "",
        "normalize": lambda x: str(x or "").strip(),
        "strategy": strategy_tech_category
    },
    "Tech_Terms": {
        "default": "",
        "normalize": lambda x: str(x or "").strip(),
        "strategy": strategy_set_join
    },
    "Relevance_Score": {
        "default": 0.0,
        "normalize": lambda x: float(x or 0.0)
    }
}
