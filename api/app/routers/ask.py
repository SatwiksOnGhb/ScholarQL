"""Natural-language question endpoints. Owned by Person B.

PLACEHOLDER: `_placeholder_answer` returns a fixed Answer built from the fake catalog.
TODO(B): replace it with `await engine.answer(question)` (or run the sync engine with
asyncio.to_thread). Logging and feedback storage are done (C, task 10); keep the
log_query() calls when swapping in the engine.
"""

import logging
import time

from fastapi import APIRouter, Request

from app import fake_data as fake
from app.config import settings
from app.errors import ApiError
from app.limits import limiter
from app.models.ask import Answer, AskRequest, AskResponse, FeedbackRequest, FeedbackResponse
from app.models.common import NOT_FOUND
from app.services.query_log import log_query, record_feedback

log = logging.getLogger(__name__)
router = APIRouter(tags=["ask"])


async def _placeholder_answer(question: str) -> Answer:
    # TODO(B): engine.answer(question)
    rows = [
        [p["title"], p["year"], fake.VENUES[p["venue_id"]]["name"]]
        for p in fake.PAPERS.values()
        if p["year"] == 2020
    ]
    return Answer(
        sql=(
            "SELECT p.title, p.year, v.name AS venue\n"
            "FROM paper p JOIN venue v ON v.venue_id = p.venue_id\n"
            "WHERE p.year = 2020\nORDER BY p.title\nLIMIT 100"
        ),
        columns=["title", "year", "venue"],
        rows=rows,
        route="sql",
        explanation=f'Placeholder answer for "{question}": papers published in 2020.',
        attempts=1,
        latency_ms=0,
    )


@router.post("/ask")
@limiter.limit(settings.rate_limit_heavy)  # each question costs LLM quota
async def ask(request: Request, body: AskRequest) -> AskResponse:
    question = body.question.strip()
    start = time.perf_counter()
    try:
        answer = await _placeholder_answer(question)
    except Exception as exc:
        # Log failures too: the analytics page reports failure reasons
        latency_ms = round((time.perf_counter() - start) * 1000)
        await log_query(question, None, latency_ms=latency_ms, error=f"{type(exc).__name__}: {exc}")
        log.exception("engine failed")
        raise ApiError(502, "engine_error", "Couldn't answer that question") from exc

    latency_ms = round((time.perf_counter() - start) * 1000)
    answer.latency_ms = latency_ms
    query_id = await log_query(question, answer, latency_ms=latency_ms)
    return AskResponse(**answer.model_dump(), query_id=query_id)


@router.post("/feedback", responses=NOT_FOUND)
async def feedback(body: FeedbackRequest) -> FeedbackResponse:
    """Thumbs up/down on an answer. Sending feedback again replaces the earlier verdict."""
    await record_feedback(body.query_id, body.correct, body.comment)
    return FeedbackResponse(ok=True)
