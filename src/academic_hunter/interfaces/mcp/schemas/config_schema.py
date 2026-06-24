from typing import Dict, Optional, List
from pydantic import BaseModel, Field

class SearchConfigUpdate(BaseModel):
    topic: Optional[str] = Field(
        None,
        description="A short name to describe this configuration (e.g. 'Blockchain Gov 2023'). Used for database records."
    )
    research_strategy: Optional[str] = Field(
        None,
        description="Write a paragraph detailing your research plan. Describe the taxonomy pillars (e.g., Architecture, Core, Performance) and list the jargon you discovered on the web."
    )
    settings: Optional[Dict] = Field(
        None, 
        description="General system settings. E.g., {'min_relevance_score': 3.5, 'start_year': 2021, 'limit_per_query': 100}. DO NOT put API keys here."
    )
    anchors: Optional[Dict] = Field(
        None, 
        description="Mandatory keyword groups. At least one term from EACH group must be in the article. E.g., {'Settlement': ['SWIFT', 'CHIPS', 'ISO 20022'], 'Wallets': ['Alipay', 'Paypal']}"
    )
    technical_strings: Optional[Dict] = Field(
        None, 
        description="Taxonomy to categorize technical_weights. MUST have at least 4 categories (e.g., 'Comparative', 'Core_Architecture', 'Operational_Performance')."
    )
    technical_weights: Optional[Dict] = Field(
        None, 
        description="CRITICAL: Do NOT be lazy. You must generate an exhaustive and deep list of technical terms (ideally 30+ terms for complex topics). GOLDEN STANDARD: Use 5.0 for core niche tech (e.g., 'RAG': 5.0, 'atomic settlement': 5.0), 3.0 for protocols ('idempotency': 3.0), and 1.5 for generic/methodological terms ('taxonomy': 1.5, 'latency': 1.5)."
    )
    context_rules: Optional[Dict[str, List[str]]] = Field(
        None,
        description="NLP rules mapping ambiguous main terms to mandatory context words. If the key term is found, the article is only accepted if it contains at least one of these words. E.g., {'drex': ['cbdc', 'digital real'], 'policy': ['government']}"
    )
    keyword_only_terms: Optional[List[str]] = Field(
        None,
        description="List of generic but important keywords for fallback search. E.g., ['ledger', 'payment', 'blockchain']"
    )
    keyword_only_category: Optional[str] = Field(
        None,
        description="Aggregating category for the generic keywords. E.g., 'Consolidated_Fintech'"
    )
