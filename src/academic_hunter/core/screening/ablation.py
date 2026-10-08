"""Which signals an ingest run is allowed to score with."""

from typing import Any, Dict

DEFAULT_ABLATION_MODE = "hybrid"


def ablation_mode(settings: Dict[str, Any]) -> str:
    """The ablation mode the run was configured with, ``hybrid`` by default."""
    return settings.get("ablation", {}).get("mode", DEFAULT_ABLATION_MODE)


def semantic_scoring_enabled(settings: Dict[str, Any], screener: Any) -> bool:
    """Whether the embedding screener takes part in this run.

    ``keyword`` is the ablation that removes the semantic signal, and it is the
    only mode that does. This answers "is the semantic path on at all", which is
    a different question from "is a screener wired up": a caller that skips the
    mode check pays a model load for a run that was told not to use one.
    """
    if screener is None:
        return False
    return ablation_mode(settings) != "keyword"
