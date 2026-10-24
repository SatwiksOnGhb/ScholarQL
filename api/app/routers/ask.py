"""Natural-language question endpoints. Owned by Person B.

PLACEHOLDER: returns a fixed Answer built from the fake catalog.
TODO(B): call engine.answer(question) and return its Answer.
TODO(C, task 10): log every answer with log_query() and store feedback in query_logs.
"""

import time
import uuid

from fastapi import APIRouter, Request

from app import fake_data as fake
from app.config import settings
from app.limits import limiter
from app.models.ask import AskRequest, AskResponse, FeedbackRequest, FeedbackResponse

router = APIRouter(tags=["ask"])


@router.post("/ask")
@limiter.limit(settings.rate_limit_heavy)  # each question costs LLM quota
async def ask(request: Request, body: AskRequest) -> AskResponse:
    start = time.perf_counter()
    rows = [
        [p["title"], p["year"], fake.VENUES[p["venue_id"]]["name"]]
        for p in fake.PAPERS.values()
        if p["year"] == 2020
    ]
    return AskResponse(
        sql=(
            "SELECT p.title, p.year, v.name AS venue\n"
            "FROM paper p JOIN venue v ON v.venue_id = p.venue_id\n"
            "WHERE p.year = 2020\nORDER BY p.title\nLIMIT 100"
        ),
        columns=["title", "year", "venue"],
        rows=rows,
        route="sql",
        explanation=f'Placeholder answer for "{body.question}": papers published in 2020.',
        attempts=1,
        latency_ms=round((time.perf_counter() - start) * 1000),
        query_id=uuid.uuid4().hex,
    )


@router.post("/feedback")
async def feedback(body: FeedbackRequest) -> FeedbackResponse:
    # Accepted and dropped for now; stored in query_logs in task 10
    return FeedbackResponse(ok=True)
