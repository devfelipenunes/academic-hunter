from .paper import Paper
from .schema import FIELD_SCHEMA
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

__all__ = [
    'Paper',
    'FIELD_SCHEMA',
    'strategy_max',
    'strategy_first_non_empty',
    'strategy_longest_string',
    'strategy_set_join',
    'strategy_anchor_category',
    'strategy_tech_category',
    'strategy_venue',
    'strategy_peer_reviewed'
]
