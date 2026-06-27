from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Protocol

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .config import ApiSettings


class DatabaseProtocol(Protocol):
    async def authenticate_user(self, username: str) -> dict[str, Any] | None: ...

    async def fetch_events(
        self,
        *,
        bbox: tuple[float, float, float, float] | None,
        date_start: date,
        date_end: date,
        event_types: list[str] | None,
    ) -> list[dict[str, Any]]: ...

    async def fetch_event(self, event_id: str) -> dict[str, Any] | None: ...

    async def fetch_metadata(self) -> dict[str, Any]: ...


class PostgresDatabase:
    def __init__(self, settings: ApiSettings) -> None:
        self._pool = AsyncConnectionPool(settings.conninfo, open=False, kwargs={"row_factory": dict_row})

    async def start(self) -> None:
        await self._pool.open()

    async def stop(self) -> None:
        await self._pool.close()

    async def authenticate_user(self, username: str) -> dict[str, Any] | None:
        async with self._pool.connection() as connection, connection.cursor() as cursor:
            await cursor.execute(
                """
                SELECT id, username, password_hash, display_name, is_active
                FROM users
                WHERE username = %s
                LIMIT 1
                """,
                (username,),
            )
            return await cursor.fetchone()

    async def fetch_events(
        self,
        *,
        bbox: tuple[float, float, float, float] | None,
        date_start: date,
        date_end: date,
        event_types: list[str] | None,
    ) -> list[dict[str, Any]]:
        async with self._pool.connection() as connection, connection.cursor() as cursor:
            if bbox:
                await cursor.execute(
                    """
                    SELECT event_id_cnty, event_type, fatalities,
                           ST_X(geom) AS longitude, ST_Y(geom) AS latitude
                    FROM acled_events
                    WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
                      AND event_date BETWEEN %s AND %s
                      AND (%s::text[] IS NULL OR event_type = ANY(%s::text[]))
                    LIMIT 2000
                    """,
                    (bbox[0], bbox[1], bbox[2], bbox[3], date_start, date_end, event_types, event_types),
                )
            else:
                await cursor.execute(
                    """
                    SELECT event_id_cnty, event_type, fatalities,
                           ST_X(geom) AS longitude, ST_Y(geom) AS latitude
                    FROM acled_events
                    WHERE event_date BETWEEN %s AND %s
                      AND (%s::text[] IS NULL OR event_type = ANY(%s::text[]))
                    """,
                    (date_start, date_end, event_types, event_types),
                )
            return await cursor.fetchall()

    async def fetch_event(self, event_id: str) -> dict[str, Any] | None:
        async with self._pool.connection() as connection, connection.cursor() as cursor:
            await cursor.execute(
                """
                SELECT event_id_cnty, event_date, event_type, sub_event_type, actor1, actor2,
                       fatalities, country, admin1, admin2, admin3, location, source, notes,
                       ST_X(geom) AS longitude, ST_Y(geom) AS latitude
                FROM acled_events
                WHERE event_id_cnty = %s
                LIMIT 1
                """,
                (event_id,),
            )
            return await cursor.fetchone()

    async def fetch_metadata(self) -> dict[str, Any]:
        async with self._pool.connection() as connection, connection.cursor() as cursor:
            await cursor.execute(
                """
                SELECT MAX(event_date) AS latest_date,
                       MIN(event_date) AS earliest_date,
                       COUNT(*) AS total_events,
                       MAX(ingested_at) AS last_updated
                FROM acled_events
                """
            )
            row = await cursor.fetchone()
        return row or {
            "latest_date": None,
            "earliest_date": None,
            "total_events": 0,
            "last_updated": datetime.now(timezone.utc),
        }
