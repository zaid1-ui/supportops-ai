FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

# build-essential is needed by a few wheels that compile on install.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Requirements first so the dependency layer caches across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application packages. Note mcp_tools (not mcp — that name shadows the SDK).
COPY backend/ ./backend/
COPY agents/ ./agents/
COPY workflows/ ./workflows/
COPY rag/ ./rag/
COPY mcp_tools/ ./mcp_tools/
COPY evaluation/ ./evaluation/
COPY scripts/ ./scripts/

# Data dir is a mount point at runtime (SQLite file, Chroma, uploads).
RUN mkdir -p /app/data

EXPOSE 8000

# Seed users/tickets on first boot, then serve. `|| true` so a re-deploy against
# an existing volume (users already seeded) does not abort the container.
CMD ["sh", "-c", "python -m scripts.seed || true && uvicorn backend.app.main:app --host 0.0.0.0 --port 8000"]
