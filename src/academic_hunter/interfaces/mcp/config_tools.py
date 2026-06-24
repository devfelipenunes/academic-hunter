import json
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from academic_hunter.core.infra.config import HunterConfig
from .memory.db_manager import MCPDatabaseManager

class SearchConfigUpdate(BaseModel):
    topic: Optional[str] = Field(
        None,
        description="Um nome curto para descrever esta configuração (ex: 'Blockchain Gov 2023'). Usado para o registro no banco de dados."
    )
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
        
        # Faz backup do estado ATUAL no banco de dados antes de modificar
        db = MCPDatabaseManager()
        current_state = {
            "settings": config.settings,
            "anchors": config.anchors,
            "technical_strings": config.tech_strings,
            "technical_weights": config.tech_weights
        }
        topic_name = config_update.topic if config_update.topic else "Auto Backup"
        db.save_config(topic=f"Before {topic_name}", config_data=current_state)
        
        # Aplica as novas modificações
        if config_update.settings: config.settings.update(config_update.settings)
        if config_update.anchors: config.anchors = config_update.anchors
        if config_update.technical_strings: config.tech_strings = config_update.technical_strings
        if config_update.technical_weights: config.tech_weights = config_update.technical_weights
        
        config.save()
        
        # Salva o NOVO estado no banco de dados também
        new_state = {
            "settings": config.settings,
            "anchors": config.anchors,
            "technical_strings": config.tech_strings,
            "technical_weights": config.tech_weights
        }
        db.save_config(topic=topic_name, config_data=new_state)
        
        return "Configurações atualizadas e registradas no histórico com sucesso!"
    except Exception as e:
        return f"Error saving config.json: {str(e)}"

def list_config_history(limit: int = 5) -> str:
    """
    Lista o histórico das últimas configurações salvas no banco de dados SQLite do MCP.
    Retorna o ID, Timestamp e o Tópico. Útil para descobrir o ID de uma config passada.
    """
    try:
        db = MCPDatabaseManager()
        history = db.list_configs(limit=limit)
        if not history:
            return "Nenhum histórico de configuração encontrado."
        return json.dumps(history, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Error reading history: {str(e)}"

def restore_config_by_id(config_id: int) -> str:
    """
    Restaura o config.json do projeto inteiro usando um backup do banco de dados (pelo seu ID).
    """
    try:
        db = MCPDatabaseManager()
        config_data = db.get_config(config_id)
        if not config_data:
            return f"Error: Config ID {config_id} não encontrado."
            
        config = HunterConfig()
        if "settings" in config_data: config.settings = config_data["settings"]
        if "anchors" in config_data: config.anchors = config_data["anchors"]
        if "technical_strings" in config_data: config.tech_strings = config_data["technical_strings"]
        if "technical_weights" in config_data: config.tech_weights = config_data["technical_weights"]
        
        config.save()
        return f"Configuração ID {config_id} restaurada com sucesso no config.json!"
    except Exception as e:
        return f"Error restoring config: {str(e)}"
