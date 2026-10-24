"""Paper titles, venue and institution names for search and the reviewer finder.

These live in A's PostgreSQL tables (`paper`, `venue`, `institution`). Until they exist,
fall back to the sample metadata written by jobs/sample/fetch_openalex.py.
TODO(A): once the schema is loaded, check the column names below match, then delete the
fallback.
"""

import json
import logging
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import psycopg
from psycopg_pool import PoolTimeout

from app.config import settings
from app.db import postgres

log = logging.getLogger(__name__)

# Postgres not ready: tables missing, server down, or pool exhausted
_NOT_READY = (psycopg.errors.UndefinedTable, psycopg.OperationalError, PoolTimeout, RuntimeError)


def _plain_ints(ids: list[int]) -> list[int]:
    # PyMongo returns big IDs as bson.Int64 and small ones as int; psycopg can't send a
    # list that mixes the two, so normalise before querying PostgreSQL
    return [int(i) for i in ids]


@dataclass(frozen=True)
class PaperSummary:
    title: str
    venue_name: str | None


@dataclass(frozen=True)
class VenueCount:
    venue_id: int
    name: str
    paper_count: int


async def paper_summaries(ids: list[int]) -> dict[int, PaperSummary]:
    ids = _plain_ints(ids)
    try:
        async with postgres.get_pool().connection(timeout=2) as conn:
            cur = await conn.execute(
                "SELECT p.paper_id, p.title, v.name FROM paper p "
                "LEFT JOIN venue v ON v.venue_id = p.venue_id WHERE p.paper_id = ANY(%s)",
                (ids,),
            )
            return {pid: PaperSummary(title, venue) for pid, title, venue in await cur.fetchall()}
    except _NOT_READY as exc:
        log.debug("paper table not available (%s); using sample metadata", type(exc).__name__)
        meta = _sample_meta()
        return {
            pid: PaperSummary(meta[pid]["title"], meta[pid].get("venue_name"))
            for pid in ids
            if pid in meta
        }


async def top_venues(limit: int = 50) -> list[VenueCount]:
    try:
        async with postgres.get_pool().connection(timeout=2) as conn:
            cur = await conn.execute(
                "SELECT v.venue_id, v.name, count(*) AS n FROM paper p "
                "JOIN venue v ON v.venue_id = p.venue_id "
                "GROUP BY v.venue_id, v.name ORDER BY n DESC LIMIT %s",
                (limit,),
            )
            return [VenueCount(vid, name, n) for vid, name, n in await cur.fetchall()]
    except _NOT_READY:
        meta = _sample_meta()
        counts = Counter(m["venue_id"] for m in meta.values() if m.get("venue_id") is not None)
        names = {m["venue_id"]: m["venue_name"] for m in meta.values() if m.get("venue_id")}
        return [VenueCount(vid, names[vid], n) for vid, n in counts.most_common(limit)]


async def institution_names(ids: list[int]) -> dict[int, str]:
    if not ids:
        return {}
    ids = _plain_ints(ids)
    try:
        async with postgres.get_pool().connection(timeout=2) as conn:
            cur = await conn.execute(
                # TODO(A): check the column name (the synopsis ER says inst_id)
                "SELECT institution_id, name FROM institution WHERE institution_id = ANY(%s)",
                (ids,),
            )
            return dict(await cur.fetchall())
    except _NOT_READY:
        wanted = set(ids)
        return {
            a["institution_id"]: a["institution_name"]
            for m in _sample_meta().values()
            for a in m["authors"]
            if a.get("institution_id") in wanted and a.get("institution_name")
        }


def _sample_meta() -> dict[int, dict]:
    path = Path(settings.sample_meta_path)
    mtime = path.stat().st_mtime if path.exists() else 0.0
    return _load_sample_meta(str(path), mtime)


@lru_cache(maxsize=1)
def _load_sample_meta(path: str, mtime: float) -> dict[int, dict]:
    """Cached per file version (mtime), so re-running the sample job is picked up."""
    if not mtime:
        log.warning("No sample metadata at %s; search results will lack titles", path)
        return {}
    with open(path, encoding="utf-8") as f:
        return {m["paper_id"]: m for m in map(json.loads, f) if m}
