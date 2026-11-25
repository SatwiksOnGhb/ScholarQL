# Build context is the repo root (docker-compose.yml, render.yaml), so B's engine/ can be
# installed alongside the API. Root .dockerignore keeps the context small.
FROM python:3.12-slim

# uv installs the exact versions pinned in uv.lock
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first so this layer is cached until the lockfile or engine changes.
# The venv lives in /opt/venv so the dev bind mounts of ./app and ./engine don't hide it.
# B's engine is a path dependency (../engine in api/pyproject.toml), so it sits at /engine.
COPY api/pyproject.toml api/uv.lock ./
COPY engine/pyproject.toml /engine/pyproject.toml
COPY engine/scholarql /engine/scholarql
RUN uv sync --frozen --no-dev --no-install-project

# Bake the embedding model into the image (~65 MB) so the first search doesn't download it
ENV FASTEMBED_CACHE=/opt/fastembed \
    HF_HUB_DISABLE_SYMLINKS_WARNING=1
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/opt/fastembed')"

COPY api/app ./app

EXPOSE 8000
# Hosts like Render choose the port via $PORT (8000 locally). --proxy-headers makes uvicorn
# use the visitor's IP from X-Forwarded-For, so per-IP rate limits work behind the host's proxy.
# (docker-compose overrides this command with a --reload version for development.)
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips '*'"]
