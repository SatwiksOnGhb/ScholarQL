"""Per-IP rate limits (slowapi).

Every route gets `settings.rate_limit_default` automatically (via SlowAPIMiddleware).
Expensive routes add a stricter limit; the decorated function must take `request: Request`:

    @router.post("/ask")
    @limiter.limit(settings.rate_limit_heavy)
    async def ask(request: Request, body: AskRequest): ...
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.rate_limit_default],
    enabled=settings.rate_limit_enabled,
)
