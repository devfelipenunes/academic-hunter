FROM python:3.12-slim AS base

WORKDIR /app

# System deps for ChromaDB/ONNX
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ src/

# `ml` is here deliberately, though the documented `uvx` install leaves it out.
# The reason it is left out there does not apply here: an image is built once, so
# the 3.15 GB is paid by whoever builds it, not by a client waiting on a spawn
# with no progress bar — and an image that ships without the analysis tools is a
# worse default than one that ships large. It used to install `.[rag]`, whose
# only entry — chromadb — is already a base dependency, so the image shipped
# without any of them.
RUN pip install --no-cache-dir -e ".[ml,fulltext]"

EXPOSE 8080

# ── Stdio mode (default for MCP) ────────────────────────────────────────────
FROM base AS stdio
ENTRYPOINT ["academic-mcp", "--transport", "stdio"]

# ── SSE mode ────────────────────────────────────────────────────────────────
FROM base AS sse
ENV ACADEMIC_MCP_TRANSPORT=sse
EXPOSE 8080
ENTRYPOINT ["academic-mcp", "--transport", "sse", "--host", "0.0.0.0"]
