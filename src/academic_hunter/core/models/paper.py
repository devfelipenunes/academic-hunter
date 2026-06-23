from typing import Dict, Any
from .schema import FIELD_SCHEMA
from .utils import normalize_doi

class Paper(dict):
    """
    Rich Domain Model representing an academic paper.
    Inherits from dict to maintain 100% backward compatibility with pandas and legacy tests.
    """
    def __init__(self, data: Dict[str, Any]):
        super().__init__()
        # Populate and normalize standard fields based on schema definitions
        for field, spec in FIELD_SCHEMA.items():
            val = data.get(field)
            if val is None:
                val = spec.get("default")
            normalize_fn = spec.get("normalize")
            self[field] = normalize_fn(val) if normalize_fn else val

    @property
    def title(self) -> str:
        return self["Title"]

    @property
    def doi(self) -> str:
        return self["DOI"]

    @property
    def citations(self) -> int:
        return self["Citations"]

    @staticmethod
    def normalize_doi(doi: str) -> str:
        return normalize_doi(doi)

    def merge(self, new_data: Dict[str, Any], anchor_cat: str, tech_cat: str):
        """Merges metadata from a duplicate paper version dynamically using FIELD_SCHEMA."""
        old_source = self.get('Source')
        new_source = new_data.get('Source')
        
        for field, spec in FIELD_SCHEMA.items():
            strategy = spec.get("strategy")
            if strategy:
                old_val = self.get(field)
                new_val = new_data.get(field)
                
                # Normalize incoming new values if a normalizer is configured
                normalize_fn = spec.get("normalize")
                if normalize_fn and new_val is not None:
                    new_val = normalize_fn(new_val)
                
                self[field] = strategy(
                    old_val, new_val,
                    anchor_cat=anchor_cat,
                    tech_cat=tech_cat,
                    old_source=old_source,
                    new_source=new_source
                )
