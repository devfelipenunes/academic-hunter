from typing import Dict, Optional
from pydantic import BaseModel, Field

class SearchConfigUpdate(BaseModel):
    topic: Optional[str] = Field(
        None,
        description="Um nome curto para descrever esta configuração (ex: 'Blockchain Gov 2023'). Usado para o registro no banco de dados."
    )
    settings: Optional[Dict] = Field(
        None, 
        description="Configurações gerais. Ex: {'min_relevance_score': 3.5, 'start_year': 2023}"
    )
    anchors: Optional[Dict] = Field(
        None, 
        description="Grupos de palavras-chave obrigatórias (cada artigo DEVE ter pelo menos um termo de CADA grupo). Ex: {'Blockchain': ['DLT', 'Blockchain'], 'Government': ['CBDC', 'Gov']}"
    )
    technical_strings: Optional[Dict] = Field(
        None, 
        description="Palavras-chave técnicas para aumentar a pontuação se encontradas. Ex: {'Smart Contracts': ['Solidity', 'EVM']}"
    )
    technical_weights: Optional[Dict] = Field(
        None, 
        description="Pesos para as technical_strings (em lower case). Ex: {'solidity': 3.0, 'evm': 2.0}"
    )
