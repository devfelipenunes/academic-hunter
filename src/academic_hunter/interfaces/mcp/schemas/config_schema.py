from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class SearchConfigUpdate(BaseModel):
    topic: Optional[str] = Field(
        None,
        description="A short name to describe this configuration (e.g. 'Blockchain Gov 2023'). Used for database records."
    )
    settings: Optional[Dict] = Field(
        None,
        description=(
            "General system settings. E.g., {'min_relevance_score': 3.5, "
            "'start_year': 2021, 'limit_per_query': 100}. "
            "Set 'ranking_query' to the research question: papers are then ranked "
            "by BM25 against it instead of by domain-term count, which is what "
            "moves retrieval quality most. Optional 'rerank': {'enabled': true, "
            "'top_n': 20} reorders the top papers with a cross-encoder; it needs "
            "'ranking_query' set and stays off unless enabled is exactly true. "
            "'collection_name' is written for you from the topic, one collection "
            "per review; set it only to override that, with 3-63 characters, "
            "alphanumerics plus _ - . and an alphanumeric at each end. "
            "DO NOT put API keys here."
        )
    )
    anchors: Optional[Dict] = Field(
        None,
        description=(
            "Mandatory keyword groups. At least one term from EACH group must be in "
            "the article. E.g., {'Settlement': ['SWIFT', 'CHIPS', 'ISO 20022'], "
            "'Wallets': ['Alipay', 'Paypal']} "
            "Within a group the terms are an OR, and only the FIRST group that "
            "matches is kept -- the gate is not one term from every group. A single "
            "generic term here therefore admits every paper that uses the word, "
            "which is what fills a corpus with work from other fields. Anchor on "
            "phrases the field's own titles carry; `quick_topic_discovery` returns "
            "exactly those, counted. A term that is also in `technical_weights` and "
            "has no `context_rules` entry is admitted on the gate alone, so give it "
            "a rule or keep it out of the anchors."
        )
    )
    technical_strings: Optional[Dict] = Field(
        None,
        description=(
            "Taxonomy to categorize technical_weights. MUST have at least 4 "
            "categories (e.g., 'Comparative', 'Core_Architecture', "
            "'Operational_Performance'). "
            "These are the terms the four grid sources are QUERIED with, once per "
            "anchor x category, so a term here steers the search: one generic term "
            "widens every query of its category, and leave this empty and those "
            "sources are never queried at all. A term here that is also in "
            "`technical_weights` is scored; one that is not is asked for, printed in "
            "the Tech_Terms column, and counted for nothing."
        )
    )
    technical_weights: Optional[Dict] = Field(
        None,
        description=(
            "CRITICAL: Do NOT be lazy. You must generate an exhaustive and deep list "
            "of technical terms (ideally 30+ terms for complex topics). GOLDEN "
            "STANDARD: Use 5.0 for core niche tech (e.g., 'RAG': 5.0, 'atomic "
            "settlement': 5.0), 3.0 for protocols ('idempotency': 3.0), and 1.5 for "
            "generic/methodological terms ('taxonomy': 1.5, 'latency': 1.5). "
            "These numbers only mean something against the cut: inclusion is decided "
            "by `settings.min_inclusion_score` (5.0 by default), and a TITLE hit "
            "counts the weight times `settings.title_multiplier` (1.5 by default) "
            "while an abstract hit counts the weight alone. So 5.0 in a title is 7.5 "
            "and clears the cut by itself, while 1.5 is 2.25 and needs three more "
            "terms beside it. Leave this empty and no configured term contributes to "
            "the score at all: every paper is scored on `log10(citations + 1)`, "
            "which almost nothing clears."
        )
    )
    context_rules: Optional[Dict[str, List[str]]] = Field(
        None,
        description="NLP rules mapping ambiguous main terms to mandatory context words. The key MUST be one of your anchor terms, lowercased: the lookup is by the anchor that matched, lowercased (scorer.py validate_anchor_context), so a key that is not an anchor never fires and the rule is silently dead. When the anchor matches, the paper is accepted only if its text also contains one of the context words. E.g., with the anchor 'Drex', {'drex': ['cbdc', 'digital real', 'central bank']} keeps the Brazilian CBDC out of papers where 'Drex' is a model name."
    )
    keyword_only_terms: Optional[List[str]] = Field(
        None,
        description="List of generic but important keywords for fallback search. E.g., ['ledger', 'payment', 'blockchain']"
    )
    keyword_only_category: Optional[str] = Field(
        None,
        description="Aggregating category for the generic keywords. E.g., 'Consolidated_Fintech'"
    )
