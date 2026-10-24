FROM python:3.12-slim

# uv installs the exact versions pinned in uv.lock
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first so this layer is cached until the lockfile changes.
# The venv lives in /opt/venv so the dev bind mount of ./app doesn't hide it.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Bake the embedding model into the image (~65 MB) so the first search doesn't download it
ENV FASTEMBED_CACHE=/opt/fastembed \
    HF_HUB_DISABLE_SYMLINKS_WARNING=1
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/opt/fastembed')"

COPY app ./app

EXPOSE 8000
# Hosts like Render choose the port via $PORT (8000 locally). --proxy-headers makes uvicorn
# use the visitor's IP from X-Forwarded-For, so per-IP rate limits work behind the host's proxy.
# (docker-compose overrides this command with a --reload version for development.)
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips '*'"]
