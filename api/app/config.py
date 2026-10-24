"""App settings, read from environment variables (and the repo-root .env for local dev).

Docker Compose sets these for the api container; see docker-compose.yml and .env.example.
"""

from functools import cached_property
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# api/app/config.py -> repo root. In the container this resolves to / (no .env there; fine).
_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ROOT_ENV, extra="ignore")

    app_env: Literal["dev", "prod"] = "dev"

    # Defaults match the Docker Compose ports, so running the API on the host just works
    database_url: str = "postgresql://scholarql:scholarql@localhost:5432/scholarql"
    mongodb_uri: str = "mongodb://scholarql:scholarql@localhost:27017/?directConnection=true"
    mongodb_db: str = "scholarql"

    # Comma-separated list, e.g. "http://localhost:3000,https://scholarql.vercel.app"
    cors_origins: str = "http://localhost:3000"

    # slowapi limit strings, per client IP
    rate_limit_default: str = "60/minute"
    rate_limit_heavy: str = "10/minute"  # LLM and embedding endpoints
    rate_limit_enabled: bool = True

    @cached_property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
