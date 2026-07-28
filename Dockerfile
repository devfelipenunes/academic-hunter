FROM python:3.12-slim AS base

WORKDIR /app

# System deps for ChromaDB/ONNX
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir -e ".[rag]"

EXPOSE 8080

# ── Stdio mode (default for MCP) ────────────────────────────────────────────
FROM base AS stdio
ENTRYPOINT ["academic-mcp", "--transport", "stdio"]

# ── SSE mode ────────────────────────────────────────────────────────────────
FROM base AS sse
ENV ACADEMIC_MCP_TRANSPORT=sse
EXPOSE 8080
ENTRYPOINT ["academic-mcp", "--transport", "sse", "--host", "0.0.0.0"]
