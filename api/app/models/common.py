"""Shapes shared by every router: the error format and the health check."""

from typing import Any, Literal

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str  # machine-readable, e.g. "not_found", "validation_error", "rate_limited"
    message: str  # human-readable, safe to show in the UI
    details: Any | None = None


class ErrorResponse(BaseModel):
    """Every non-2xx response has this body."""

    error: ErrorBody


# Added to every route's OpenAPI entry so the generated web client knows the error shape
COMMON_RESPONSES: dict[int | str, dict[str, Any]] = {
    422: {"model": ErrorResponse, "description": "Invalid request"},
    429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    500: {"model": ErrorResponse, "description": "Server error"},
}
NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not found"},
}


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    postgres: Literal["ok", "down"]
    mongodb: Literal["ok", "down"]
