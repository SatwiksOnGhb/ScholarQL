"""Shapes for B's endpoints: POST /ask and POST /feedback.

`Answer` is contract 3: what the engine's answer(question) returns. Its fields are frozen;
change them only with the whole team's agreement.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

Route = Literal["sql", "semantic", "hybrid"]


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class Answer(BaseModel):
    sql: str | None = Field(description="Generated SQL; null for purely semantic answers")
    columns: list[str]
    rows: list[list[Any]]
    route: Route
    explanation: str
    attempts: int = Field(description="1 = first try worked; more = self-correction retries")
    latency_ms: int


class AskResponse(Answer):
    query_id: str | None = Field(
        None, description="ID of the query_logs entry; send it to POST /feedback"
    )


class FeedbackRequest(BaseModel):
    query_id: str
    correct: bool
    comment: str | None = Field(None, max_length=1000)


class FeedbackResponse(BaseModel):
    ok: bool = True
