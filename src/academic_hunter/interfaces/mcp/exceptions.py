"""Structured exception hierarchy for Academic Hunter MCP tools.

Every tool should raise the most specific subclass so that FastMCP
converts it into an ``isError: true`` response on the wire.
"""


class MCPToolError(Exception):
    """Base for all MCP tool errors.

    The ``code`` and the ``details`` also travel inside the message, because the
    message is the only field of an exception that reaches the client: FastMCP
    serialises ``str(exc)`` and drops the attributes. A tool that worked out which
    directory it looked in, or which alternatives existed, was computing context
    that was thrown away one frame later.

    Parameters
    ----------
    message : str
        Human-readable error description.
    code : str
        Machine-readable error code (default ``"TOOL_ERROR"``).
    details : dict | None
        Optional structured context (e.g. failed file path, HTTP status).
    """

    def __init__(
        self, message: str, code: str = "TOOL_ERROR", details: dict | None = None
    ):
        self.code = code
        self.details = details or {}
        super().__init__(self._with_context(message))

    def _with_context(self, message: str) -> str:
        """The message as the client receives it: code and details folded in.

        Only when there are details. An error raised with none keeps the exact
        message it was given, so ``str(exc)`` stays the sentence the caller wrote.
        The cost of folding is that the code stops being a structured field and
        becomes text; FastMCP offers nowhere else to put it, and a code the agent
        cannot read is the same as no code at all.
        """
        if not self.details:
            return message
        context = ", ".join(f"{key}={value}" for key, value in self.details.items())
        return f"{message} [{self.code}: {context}]"


class ConfigError(MCPToolError):
    """Configuration loading / saving / validation errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="CONFIG_ERROR", details=details)


class SearchError(MCPToolError):
    """Search-pipeline execution errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="SEARCH_ERROR", details=details)


class VectorStoreError(MCPToolError):
    """ChromaDB / vector-index errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="VECTOR_STORE_ERROR", details=details)


class DiscoveryError(MCPToolError):
    """External-API (Semantic Scholar, etc.) errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="DISCOVERY_ERROR", details=details)


class ObsidianError(MCPToolError):
    """Obsidian vault export errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="OBSIDIAN_ERROR", details=details)


class WritingError(MCPToolError):
    """Article outline / drafting errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="WRITING_ERROR", details=details)


class CitationError(MCPToolError):
    """Citation verification errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="CITATION_ERROR", details=details)
