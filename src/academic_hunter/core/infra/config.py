"""Configuration management for Academic Hunter.

Loads and caches JSON configuration with environment variable overrides.
Supports validation and change tracking for MCP config history.
"""

import json
import os
import time
from pathlib import Path
from typing import Dict, Any, List, Set, Optional

from .history import ConfigHistory


class HunterConfig:
    """Handles JSON configuration loading, environment variables, pacing delays, and default fallback parameters.

    Features:
    - Lazy-loading with cache invalidation via mtime check
    - Environment variable overrides (prefixed with ACADEMIC_HUNTER_)
    - Change history tracking for MCP undo/restore (via ConfigHistory)
    - Type-validated accessors for all config sections
    """

    def __init__(self, config_path: str = 'config.json',
                 pacing_defaults: Optional[Dict[str, float]] = None):
        """
        Args:
            config_path: Path to the JSON configuration file.
            pacing_defaults: Domain-to-delay mapping derived from the connector
                set by the composition root. Defaults to empty, so a config built
                without it simply has no pacing entries.
        """
        self.config_path = Path(config_path)
        if not self.config_path.exists():
            # Fallback for MCP servers running from different CWDs
            project_root = Path(__file__).parent.parent.parent.parent.parent
            fallback_path = project_root / 'config.json'
            if fallback_path.exists():
                self.config_path = fallback_path

        self._mtime: float = 0.0
        self._raw: Dict[str, Any] = {}

        # Typed accessors (populated by load())
        self.settings: Dict[str, Any] = {}
        self.anchors: Dict[str, list] = {}
        self.tech_strings: Dict[str, list] = {}
        self.tech_weights: Dict[str, float] = {}
        self.context_rules: Dict[str, List[str]] = {}
        self.keyword_only_terms: List[str] = []
        self.keyword_only_category: str = ""
        self.blocked_sources: Set[str] = set()
        # Pacing defaults are supplied by the composition root, which is the only
        # layer that knows the connector set. This used to be read from the
        # plugin registry here, which made the domain depend on its adapters.
        self.pacing_delays: Dict[str, float] = dict(pacing_defaults or {})

        # Initial load
        self.load()

    def _check_stale(self) -> bool:
        """Check if config file has been modified since last load."""
        if not self.config_path.exists():
            return False
        current_mtime = self.config_path.stat().st_mtime
        return current_mtime > self._mtime + 0.1  # 100ms tolerance

    def load(self, force: bool = False):
        """Load config from JSON file, respecting cache unless forced.

        Args:
            force: If True, bypass mtime cache and reload unconditionally.
        """
        if not force and self._raw and not self._check_stale():
            return

        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found at '{self.config_path}'. "
                "Copy config.example.json to config.json and customize it."
            )

        with open(self.config_path, 'r', encoding='utf-8') as f:
            self._raw = json.load(f)

        # Save pre-override snapshot for history tracking
        raw_copy = json.loads(json.dumps(self._raw))

        self._apply_env_overrides()

        self.settings = self._raw.get('settings', {})
        self.anchors = self._raw.get('anchors', {})
        self.tech_strings = self._raw.get('technical_strings', {})
        self.tech_weights = self._raw.get('technical_weights', {})
        self.context_rules = self._raw.get('context_rules', {})
        self.keyword_only_terms = self._raw.get('keyword_only_terms', [])
        self.keyword_only_category = self._raw.get('keyword_only_category', '')

        # Default fallbacks for keyword-only search configurations
        if not self.keyword_only_terms:
            self.keyword_only_terms = [
                "ledger", "payment", "interoperability", "settlement", "blockchain"
            ]
        if not self.keyword_only_category:
            self.keyword_only_category = "Consolidated_Fintech"

        self._mtime = time.time()
        self._push_history(raw_copy)

    def _apply_env_overrides(self):
        """Override config values with environment variables prefixed ACADEMIC_HUNTER_.

        Supports dot-notation paths like ACADEMIC_HUNTER_settings__min_relevance_score.
        Uses double underscore as path separator (compatible with systemd env files).
        """
        prefix = "ACADEMIC_HUNTER_"
        for key, value in sorted(os.environ.items()):
            if not key.startswith(prefix):
                continue
            path = key[len(prefix):].lower().split("__")
            target = self._raw
            for part in path[:-1]:
                if part not in target:
                    target[part] = {}
                target = target[part]
            # Try to preserve types
            raw_val: Any = value
            if value.lower() in ("true", "false"):
                raw_val = value.lower() == "true"
            else:
                try:
                    if "." in value:
                        raw_val = float(value)
                    else:
                        raw_val = int(value)
                except (ValueError, TypeError):
                    pass
            target[path[-1]] = raw_val

    def _push_history(self, snapshot_data: Dict[str, Any]):
        """Store a config snapshot for undo/restore functionality."""
        ConfigHistory.push(snapshot_data)

    def min_inclusion_score(self) -> float:
        """Threshold for the mode-dependent **inclusion** score (``_hybrid_score``).

        This is deliberately not the same setting as ``min_relevance_score``.
        The two scores live on different scales:

        - ``_hybrid_score`` — computed at ingest by
          ``AcademicScorer.compute_hybrid_score``. Its scale depends on the
          ablation mode: keyword mode yields the raw regex score (unbounded),
          embedding mode yields ``sqrt(cosine) * 10`` in [0, 10], hybrid adds
          ``kw * 0.3`` on top of that. Used to decide *whether a paper enters*.
        - ``Relevance_Score`` — written once, after the whole run, by
          ``RecomputeRanksStep``. Rank-normalised to [0, 10] and therefore
          independent of the ablation mode. Used for ordering and reporting.

        Comparing one constant against both scales is what made enriched papers
        systematically outrank the rest, and what made the ablation modes
        incomparable. Falls back to ``min_relevance_score`` so existing
        configurations keep their behaviour.
        """
        return float(
            self.settings.get(
                "min_inclusion_score", self.settings.get("min_relevance_score", 5.0)
            )
        )

    def screener_config(self) -> Dict[str, Any]:
        """Payload the semantic screener expects.

        Single source of truth for this dict shape. It used to be rebuilt inline
        in five places (validators, resolvers, pipeline steps), so a field added
        here could be silently missing everywhere else.
        """
        return {
            "anchors": self.anchors,
            "technical_strings": self.tech_strings,
            "technical_weights": self.tech_weights,
        }

    def save(self):
        """Persist current config back to the JSON file."""
        config = {
            "settings": self.settings,
            "anchors": self.anchors,
            "technical_strings": self.tech_strings,
            "technical_weights": self.tech_weights,
            "context_rules": self.context_rules,
            "keyword_only_terms": self.keyword_only_terms,
            "keyword_only_category": self.keyword_only_category,
        }
        # Preserve any extra keys from the raw config
        for k in self._raw:
            if k not in config and k.startswith("_"):
                config[k] = self._raw[k]

        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)

        # Update mtime so cache knows it's fresh
        self._mtime = time.time()

    def get_full_config(self) -> Dict[str, Any]:
        """Return the full config dict (useful for MCP tools)."""
        return {
            "settings": self.settings,
            "anchors": self.anchors,
            "technical_strings": self.tech_strings,
            "technical_weights": self.tech_weights,
            "context_rules": self.context_rules,
            "keyword_only_terms": self.keyword_only_terms,
            "keyword_only_category": self.keyword_only_category,
        }

    @classmethod
    def get_history(cls) -> List[Dict[str, Any]]:
        """Get config change history for MCP tool display."""
        return ConfigHistory.list_history()
