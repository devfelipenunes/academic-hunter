from typing import Dict, Any
from .utils import normalize_doi
from .strategies import (
    strategy_max,
    strategy_first_non_empty,
    strategy_longest_string,
    strategy_set_join,
    strategy_anchor_category,
    strategy_tech_category,
    strategy_venue,
    strategy_peer_reviewed
)

FIELD_SCHEMA: Dict[str, Dict[str, Any]] = {
    "Title": {
        "default": "",
        "normalize": lambda x: str(x or "").strip().replace('\n', ' ')
    },
    "Abstract": {
        "default": "",
        "normalize": lambda x: str(x or "").strip().replace('\n', ' '),
        "strategy": strategy_longest_string
    },
    "Year": {
        "default": "N/A",
        "normalize": lambda x: x if x is not None else "N/A"
    },
    "URL": {
        "default": "",
        "normalize": lambda x: str(x or "").strip(),
        "strategy": strategy_first_non_empty
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
        "normalize": lambda x: str(x or "").strip()
    },
    "Tech_Category": {
        "default": "",
        "normalize": lambda x: str(x or "").strip(),
        "strategy": strategy_tech_category
    },
    "Tech_Terms": {
        "default": "",
        "normalize": lambda x: str(x or "").strip()
    },
    "Relevance_Score": {
        "default": 0.0,
        "normalize": lambda x: float(x or 0.0)
    }
}
