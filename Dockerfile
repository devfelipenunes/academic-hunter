FROM python:3.12-slim AS base

WORKDIR /app

# System deps for ChromaDB/ONNX
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ src/

# `ml` is what the analysis tools actually need (sentence-transformers,
# scikit-learn, umap-learn, bertopic). It used to install `.[rag]`, whose only
# entry — chromadb — is already a base dependency, so the image shipped without
# any of them and the tools degraded silently behind their fallbacks.
RUN pip install --no-cache-dir -e ".[ml]"

EXPOSE 8080

# ── Stdio mode (default for MCP) ────────────────────────────────────────────
FROM base AS stdio
ENTRYPOINT ["academic-mcp", "--transport", "stdio"]

# ── SSE mode ────────────────────────────────────────────────────────────────
FROM base AS sse
ENV ACADEMIC_MCP_TRANSPORT=sse
EXPOSE 8080
ENTRYPOINT ["academic-mcp", "--transport", "sse", "--host", "0.0.0.0"]
