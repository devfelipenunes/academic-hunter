"""Pydantic schemas for MCP tool parameters and responses."""

from .config_schema import SearchConfigUpdate
from .responses import ToolResult, ConfigData, SearchResult, PaperData

__all__ = [
    "SearchConfigUpdate",
    "ToolResult",
    "ConfigData",
    "SearchResult",
    "PaperData",
]
