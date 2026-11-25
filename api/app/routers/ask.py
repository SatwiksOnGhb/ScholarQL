"""Natural-language question endpoints: B's engine behind POST /ask, plus feedback.

Every question is logged to MongoDB query_logs (answers and failures), and the log's ID is
returned as `query_id` for POST /feedback.
"""

import logging
import time

from fastapi import APIRouter, Request

from app.config import settings
from app.errors import ApiError
from app.limits import limiter
from app.models.ask import AskRequest, AskResponse, FeedbackRequest, FeedbackResponse
from app.models.common import NOT_FOUND, ErrorResponse
from app.services import engine
from app.services.query_log import log_query, record_feedback

log = logging.getLogger(__name__)
router = APIRouter(tags=["ask"])


ASK_ERRORS = {
    422: {"model": ErrorResponse, "description": "The engine can't answer this question"},
    502: {"model": ErrorResponse, "description": "The engine failed"},
    503: {"model": ErrorResponse, "description": "A database is unavailable"},
}


@router.post("/ask", responses=ASK_ERRORS)
@limiter.limit(settings.rate_limit_heavy)  # each question costs LLM quota
async def ask(request: Request, body: AskRequest) -> AskResponse:
    question = body.question.strip()
    start = time.perf_counter()
    try:
        answer = await engine.answer(question)
    except engine.EngineError as exc:
        # Unsupported wording or rejected SQL: log it, and show the engine's explanation
        latency_ms = round((time.perf_counter() - start) * 1000)
        await log_query(question, None, latency_ms=latency_ms, error=f"{type(exc).__name__}: {exc}")
        if isinstance(exc, engine.DocumentsUnavailable):
            raise ApiError(503, "service_unavailable", str(exc)) from exc
        raise ApiError(422, "unanswerable", str(exc)) from exc
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
