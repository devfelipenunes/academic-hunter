import json
from typing import Dict, List, Optional
from academic_hunter.core.infra.config import HunterConfig
from ..schemas.config_schema import SearchConfigUpdate
from ..memory.sqlite_store import MCPDatabaseManager

def read_config() -> str:
    """
    Returns the current full search configuration from config.json.
    Use this tool to check which anchors or technical_strings are currently configured.
    """
    try:
        config = HunterConfig()
        data = {
            "settings": config.settings,
            "anchors": config.anchors,
            "technical_strings": config.tech_strings,
            "technical_weights": config.tech_weights,
            "context_rules": config.context_rules,
            "keyword_only_terms": config.keyword_only_terms,
            "keyword_only_category": config.keyword_only_category
        }
        return json.dumps(data, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Error reading config: {str(e)}"

def update_config(config_update: SearchConfigUpdate) -> str:
    """
    Updates the Hunter search configuration.
    Use this tool WHENEVER the user asks to research a new topic.
    
    RESEARCH AGENT INSTRUCTIONS:
    1. Extract main terms into 'anchors' and secondary terms into 'technical_strings'.
    2. Identify ambiguous terms (e.g., 'policy') and create rules in 'context_rules' with mandatory disambiguation words.
    3. Important but generic words should go into 'keyword_only_terms' with an aggregating category in 'keyword_only_category'.
    4. When running this tool for a new topic, old NLP parameters will be erased. Therefore, generate the complete NLP configuration.
    5. CRITICAL: Do NOT be lazy. You must generate an EXHAUSTIVE list of technical terms (30+ for complex topics) to prevent a shallow search.
    """
    try:
        config = HunterConfig()
        
        db = MCPDatabaseManager()
        current_state = {
            "settings": config.settings,
            "anchors": config.anchors,
            "technical_strings": config.tech_strings,
            "technical_weights": config.tech_weights,
            "context_rules": config.context_rules,
            "keyword_only_terms": config.keyword_only_terms,
            "keyword_only_category": config.keyword_only_category
        }
        topic_name = config_update.topic if config_update.topic else "Auto Backup"
        db.save_config(topic=f"Before {topic_name}", config_data=current_state)
        
        if config_update.settings: config.settings.update(config_update.settings)
        if config_update.anchors: config.anchors = config_update.anchors
        if config_update.technical_strings: config.tech_strings = config_update.technical_strings
        if config_update.technical_weights: config.tech_weights = config_update.technical_weights
        
        config.context_rules = config_update.context_rules if config_update.context_rules else {}
        config.keyword_only_terms = config_update.keyword_only_terms if config_update.keyword_only_terms else []
        config.keyword_only_category = config_update.keyword_only_category if config_update.keyword_only_category else ""
        
        config.save()
        new_state = {
            "settings": config.settings,
            "anchors": config.anchors,
            "technical_strings": config.tech_strings,
            "technical_weights": config.tech_weights,
            "context_rules": config.context_rules,
            "keyword_only_terms": config.keyword_only_terms,
            "keyword_only_category": config.keyword_only_category
        }
        db.save_config(topic=topic_name, config_data=new_state)
        
        return "Configuration updated and saved to history successfully!"
    except Exception as e:
        return f"Error saving config.json: {str(e)}"

def list_config_history(limit: int = 5) -> str:
    """
    Lists the history of the last saved configurations in the MCP SQLite database.
    Returns the ID, Timestamp, and Topic. Useful for finding the ID of a past config.
    """
    try:
        db = MCPDatabaseManager()
        history = db.list_configs(limit=limit)
        if not history:
            return "No configuration history found."
        return json.dumps(history, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Error reading history: {str(e)}"

def restore_config_by_id(config_id: int) -> str:
    """
    Restores the full project config.json using a database backup (by its ID).
    """
    try:
        db = MCPDatabaseManager()
        config_data = db.get_config(config_id)
        if not config_data:
            return f"Error: Config ID {config_id} not found."
            
        config = HunterConfig()
        if "settings" in config_data: config.settings = config_data["settings"]
        if "anchors" in config_data: config.anchors = config_data["anchors"]
        if "technical_strings" in config_data: config.tech_strings = config_data["technical_strings"]
        if "technical_weights" in config_data: config.tech_weights = config_data["technical_weights"]
        if "context_rules" in config_data: config.context_rules = config_data["context_rules"]
        if "keyword_only_terms" in config_data: config.keyword_only_terms = config_data["keyword_only_terms"]
        if "keyword_only_category" in config_data: config.keyword_only_category = config_data["keyword_only_category"]
        
        config.save()
        return f"Configuration ID {config_id} restored successfully to config.json!"
    except Exception as e:
        return f"Error restoring config: {str(e)}"
