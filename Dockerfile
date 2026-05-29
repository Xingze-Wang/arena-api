FROM python:3.12-slim

WORKDIR /app

# System deps kept minimal; cryptography ships wheels for slim.
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e . || pip install --no-cache-dir \
    "fastapi>=0.115" "uvicorn[standard]>=0.32" "sqlmodel>=0.0.22" \
    "httpx>=0.27" "anthropic>=0.40" "pydantic-settings>=2.5" \
    "python-multipart>=0.0.12" "cryptography>=43.0"

COPY . .
RUN pip install --no-cache-dir -e .

# Fly sets PORT; default 8001 for local docker run.
ENV PORT=8001
ENV ARENA_DB_PATH=/data/arena.db

# /data is a Fly volume mount (persists SQLite + encrypted holdouts across deploys).
RUN mkdir -p /data

EXPOSE 8001

# Encrypt any plaintext holdouts at boot (idempotent), then serve.
CMD ["sh", "-c", "python scripts/encrypt_holdouts.py 2>/dev/null; uvicorn arena_api.main:app --host 0.0.0.0 --port ${PORT}"]
