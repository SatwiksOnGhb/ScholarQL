"""Reviewer finder with a conflict-of-interest check. Owned by Person C.

PLACEHOLDER: suggests authors from the fake catalog, dropping the submitting authors and
their co-authors. Task 9 replaces this with author-profile vector search plus coauthors().
"""

from fastapi import APIRouter, Request

from app import fake_data as fake
from app.config import settings
from app.limits import limiter
from app.models.reviewers import MatchingPaper, Reviewer, ReviewerRequest, ReviewerResponse

router = APIRouter(tags=["reviewers"])


@router.post("/reviewers")
@limiter.limit(settings.rate_limit_heavy)  # embeds the abstract on every call
async def find_reviewers(request: Request, body: ReviewerRequest) -> ReviewerResponse:
    submitted = set(body.author_ids)
    coauthors = {
        a for p in fake.PAPERS.values() if submitted & set(p["author_ids"]) for a in p["author_ids"]
    }
    excluded = sorted((submitted | coauthors) & fake.AUTHORS.keys())

    reviewers = []
    for rank, author in enumerate(
        a for a in fake.AUTHORS.values() if a["author_id"] not in excluded
    ):
        score = round(0.9 - 0.05 * rank, 3)
        papers = [p for p in fake.PAPERS.values() if author["author_id"] in p["author_ids"]]
        reviewers.append(
            Reviewer(
                author_id=author["author_id"],
                name=author["name"],
                institution_id=author["institution_id"],
                institution_name=fake.INSTITUTIONS[author["institution_id"]]["name"],
                score=score,
                matching_papers=[
                    MatchingPaper(paper_id=p["paper_id"], title=p["title"], score=score)
                    for p in papers
                ],
            )
        )
    return ReviewerResponse(reviewers=reviewers[: body.k], excluded_author_ids=excluded)
