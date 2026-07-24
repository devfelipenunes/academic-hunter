"""Pydantic models for structured MCP tool responses.

These schemas are used internally by tools for consistent data formatting.
Tools still return ``str`` to maintain backward compatibility with MCP clients,
but the data is assembled through these models for validation.
"""

from typing import Any, Optional
from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    """Generic result envelope for any MCP tool."""

    success: bool
    message: str
    data: Optional[dict[str, Any]] = None


class ConfigData(ToolResult):
    """Result for configuration-related tools."""
    pass


class SearchResult(ToolResult):
    """Result for search-pipeline tools."""
    pass


class PaperData(BaseModel):
    """Structured metadata for a single academic paper."""

    doi: str
    title: str
    abstract: Optional[str] = None
    year: Optional[int] = None
    source: Optional[str] = None
    url: Optional[str] = None
    venue: Optional[str] = None
    semantic_relevance: Optional[float] = Field(None, ge=0.0, le=1.0)
    score: Optional[float] = None
