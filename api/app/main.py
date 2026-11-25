"""ScholarQL API entry point: app setup, middleware, error handlers and routers."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.db import mongo, postgres
from app.errors import register_error_handlers
from app.limits import limiter
from app.models.common import COMMON_RESPONSES, HealthResponse
from app.routers import admin, ask, papers, reviewers, search
from app.services import engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Runs once at startup (before `yield`) and once at shutdown (after it)
    await postgres.open_pool()
    mongo.connect()
    engine.configure()
    yield
    engine.close()
    await postgres.close_pool()
    await mongo.close()


app = FastAPI(
    title="ScholarQL API",
    version="0.1.0",
    lifespan=lifespan,
    responses=COMMON_RESPONSES,
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
# Added last = outermost, so even 429/500 responses get CORS headers
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_error_handlers(app)

app.include_router(papers.router)  # A
app.include_router(ask.router)  # B
app.include_router(search.router)  # C
app.include_router(reviewers.router)  # C
app.include_router(admin.router)  # C


@app.get("/health", tags=["meta"])
@limiter.exempt
async def health(request: Request) -> HealthResponse:
    # Always 200 so Docker keeps the API up; the body says which database is down
    pg_ok, mongo_ok = await asyncio.gather(postgres.ping(), mongo.ping())
    return HealthResponse(
        status="ok" if pg_ok and mongo_ok else "degraded",
        postgres="ok" if pg_ok else "down",
        mongodb="ok" if mongo_ok else "down",
    )
