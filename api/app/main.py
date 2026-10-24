"""ScholarQL API entry point.

Task 1 only needs the container to start and answer a health check.
Config, DB connections, error format, rate limits and routers come in task 3.
"""

from fastapi import FastAPI

app = FastAPI(title="ScholarQL API", version="0.1.0")


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
