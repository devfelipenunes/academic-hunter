import json
from pathlib import Path
from typing import Dict, Any, Set
from ...plugins.connectors import CONNECTORS

class HunterConfig:
    """Handles JSON configuration loading, environment variables, pacing delays, and default fallback parameters."""

    def __init__(self, config_path: str = 'config.json'):
        self.config_path = Path(config_path)
        self.settings: Dict[str, Any] = {}
        self.anchors: Dict[str, list] = {}
        self.tech_strings: Dict[str, list] = {}
        self.tech_weights: Dict[str, float] = {}
        self.blocked_sources: Set[str] = set()
        self.pacing_delays: Dict[str, float] = {}
        
        # Populate pacing delays dynamically from connector plugins registry
        for name, connector_cls in CONNECTORS.items():
            domain = getattr(connector_cls, 'domain', '')
            delay = getattr(connector_cls, 'default_delay', 1.5)
            if domain:
                self.pacing_delays[domain] = delay
                
        self.load()

    def load(self):
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found at '{self.config_path}'.")
            
        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            self.settings = config.get('settings', {})
            self.anchors = config.get('anchors', {})
            self.tech_strings = config.get('technical_strings', {})
            self.tech_weights = config.get('technical_weights', {})
            
            # Default fallbacks for keyword-only search configurations
            if "keyword_only_terms" not in self.settings:
                self.settings["keyword_only_terms"] = [
                    "ledger", "payment", "interoperability", "settlement", "blockchain"
                ]
            if "keyword_only_category" not in self.settings:
                self.settings["keyword_only_category"] = "Consolidated_Fintech"

    def save(self):
        config = {
            "settings": self.settings,
            "anchors": self.anchors,
            "technical_strings": self.tech_strings,
            "technical_weights": self.tech_weights
        }
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
