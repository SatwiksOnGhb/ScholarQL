"""Paper titles, venue and institution names for search and the reviewer finder.

These live in A's PostgreSQL tables (`paper`, `venue`, `institution`). If PostgreSQL is down or
empty, fall back to the optional MongoDB collection `sample_paper_meta`, which
jobs/embed/embed_papers.py fills when it runs on the OpenAlex sample without PostgreSQL.
"""

import logging
from dataclasses import dataclass

import psycopg
from psycopg_pool import PoolTimeout
from pymongo.errors import PyMongoError

from app.db import mongo, postgres

log = logging.getLogger(__name__)

# Postgres not ready: tables missing, server down, or pool exhausted
NOT_READY = (psycopg.errors.UndefinedTable, psycopg.OperationalError, PoolTimeout, RuntimeError)


def _sample_meta():
    """Fallback collection for running without PostgreSQL."""
    return mongo.get_db().sample_paper_meta


@dataclass(frozen=True)
class PaperSummary:
    title: str
    venue_name: str | None


@dataclass(frozen=True)
class VenueCount:
    venue_id: str
    name: str
    paper_count: int


async def paper_summaries(ids: list[str]) -> dict[str, PaperSummary]:
    if not ids:
        return {}
    try:
        async with postgres.get_pool().connection(timeout=2) as conn:
            cur = await conn.execute(
                "SELECT p.paper_id, p.title, v.name FROM paper p "
                "LEFT JOIN venue v ON v.venue_id = p.venue_id WHERE p.paper_id = ANY(%s)",
                (ids,),
            )
            found = {pid: PaperSummary(title, venue) for pid, title, venue in await cur.fetchall()}
            if found:
                return found
    except NOT_READY as exc:
        log.debug("paper table not available (%s); using sample_paper_meta", type(exc).__name__)
    try:
        cursor = _sample_meta().find({"_id": {"$in": ids}}, {"title": 1, "venue_name": 1})
        return {d["_id"]: PaperSummary(d["title"], d.get("venue_name")) async for d in cursor}
    except PyMongoError as exc:
        log.warning("sample_paper_meta unavailable: %s", exc)
        return {}


async def top_venues(limit: int = 50) -> list[VenueCount]:
    try:
        async with postgres.get_pool().connection(timeout=2) as conn:
            cur = await conn.execute(
                "SELECT v.venue_id, v.name, count(*) AS n FROM paper p "
                "JOIN venue v ON v.venue_id = p.venue_id "
                "GROUP BY v.venue_id, v.name ORDER BY n DESC LIMIT %s",
                (limit,),
            )
            venues = [VenueCount(vid, name, n) for vid, name, n in await cur.fetchall()]
            if venues:
                return venues
    except NOT_READY:
        pass
    pipeline = [
        {"$match": {"venue_id": {"$ne": None}}},
        {"$group": {"_id": "$venue_id", "name": {"$first": "$venue_name"}, "n": {"$sum": 1}}},
        {"$sort": {"n": -1, "_id": 1}},
        {"$limit": limit},
    ]
    try:
        cursor = await _sample_meta().aggregate(pipeline)
        return [VenueCount(d["_id"], d["name"], d["n"]) async for d in cursor]
    except PyMongoError as exc:
        log.warning("sample_paper_meta unavailable: %s", exc)
        return []


async def institution_names(ids: list[str]) -> dict[str, str]:
    if not ids:
        return {}
    try:
        async with postgres.get_pool().connection(timeout=2) as conn:
            cur = await conn.execute(
                "SELECT institution_id, name FROM institution WHERE institution_id = ANY(%s)",
                (ids,),
            )
            found = dict(await cur.fetchall())
            if found:
                return found
    except NOT_READY:
        pass
    pipeline = [
        {"$match": {"institutions.institution_id": {"$in": ids}}},
        {"$unwind": "$institutions"},
        {"$match": {"institutions.institution_id": {"$in": ids}}},
        {
            "$group": {
                "_id": "$institutions.institution_id",
                "name": {"$first": "$institutions.name"},
            }
        },
    ]
    try:
        cursor = await _sample_meta().aggregate(pipeline)
        return {d["_id"]: d["name"] async for d in cursor}
    except PyMongoError as exc:
        log.warning("sample_paper_meta unavailable: %s", exc)
        return {}
