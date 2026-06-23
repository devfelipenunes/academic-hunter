import json
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from academic_hunter.core.infra.config import HunterConfig

class SearchConfigUpdate(BaseModel):
    settings: Optional[Dict] = Field(
        None, 
        description="Configurações gerais. Ex: {'min_relevance_score': 3.5, 'start_year': 2023}"
    )
    anchors: Optional[Dict[str, List[str]]] = Field(
        None, 
        description="Categorias principais de busca. Ex: {'Blockchain_Gov': ['CBDC', 'E-government', 'Smart Contracts']}"
    )
    technical_strings: Optional[Dict[str, List[str]]] = Field(
        None, 
        description="Termos técnicos secundários para filtrar. Ex: {'Consensus': ['Proof of Authority', 'Hyperledger']}"
    )
    technical_weights: Optional[Dict[str, float]] = Field(
        None, 
        description="Pesos para palavras específicas. Ex: {'cbdc': 5.0, 'hyperledger': 4.0}"
    )

def read_config() -> str:
    """
    Reads the current search configurations.
    Useful for inspecting the current search parameters (keywords, limit_per_source, year_start, etc) before updating them.
    """
    try:
        config = HunterConfig()
        data = {
            "settings": config.settings,
            "anchors": config.anchors,
            "technical_strings": config.tech_strings,
            "technical_weights": config.tech_weights
        }
        return json.dumps(data, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Error reading config: {str(e)}"

def update_config(config_update: SearchConfigUpdate) -> str:
    """
    Atualiza as configurações de busca do Hunter.
    Use esta ferramenta SEMPRE que o usuário pedir para pesquisar um novo tema.
    Traduza o pedido do usuário em 'anchors' e 'technical_strings' relevantes e atualize o config.json.
    """
    try:
        config = HunterConfig()
        
        if config_update.settings: config.settings.update(config_update.settings)
        if config_update.anchors: config.anchors = config_update.anchors
        if config_update.technical_strings: config.tech_strings = config_update.technical_strings
        if config_update.technical_weights: config.tech_weights = config_update.technical_weights
        
        config.save()
        return "Configurações atualizadas com sucesso! Você já pode usar a ferramenta run_search."
    except Exception as e:
        return f"Error saving config.json: {str(e)}"
