from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
import json
from typing import Any, Iterable, Iterator, Sequence

import bcrypt
import psycopg
from psycopg.rows import dict_row

from .config import IngestSettings


UPSERT_SQL = """
INSERT INTO acled_events (
    event_id_cnty, event_date, year, time_precision, disorder_type, event_type,
    sub_event_type, actor1, assoc_actor_1, inter1, actor2, assoc_actor_2,
    inter2, interaction, civilian_targeting, iso, region, country, admin1,
    admin2, admin3, location, latitude, longitude, geo_precision, source,
    source_scale, notes, fatalities, tags, timestamp, population_best,
    population_1km, population_2km, population_5km, geom
)
VALUES (
    %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s,
    %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326)
)
ON CONFLICT (event_id_cnty) DO UPDATE SET
    event_date = EXCLUDED.event_date,
    year = EXCLUDED.year,
    time_precision = EXCLUDED.time_precision,
    disorder_type = EXCLUDED.disorder_type,
    event_type = EXCLUDED.event_type,
    sub_event_type = EXCLUDED.sub_event_type,
    actor1 = EXCLUDED.actor1,
    assoc_actor_1 = EXCLUDED.assoc_actor_1,
    inter1 = EXCLUDED.inter1,
    actor2 = EXCLUDED.actor2,
    assoc_actor_2 = EXCLUDED.assoc_actor_2,
    inter2 = EXCLUDED.inter2,
    interaction = EXCLUDED.interaction,
    civilian_targeting = EXCLUDED.civilian_targeting,
    iso = EXCLUDED.iso,
    region = EXCLUDED.region,
    country = EXCLUDED.country,
    admin1 = EXCLUDED.admin1,
    admin2 = EXCLUDED.admin2,
    admin3 = EXCLUDED.admin3,
    location = EXCLUDED.location,
    latitude = EXCLUDED.latitude,
    longitude = EXCLUDED.longitude,
    geo_precision = EXCLUDED.geo_precision,
    source = EXCLUDED.source,
    source_scale = EXCLUDED.source_scale,
    notes = EXCLUDED.notes,
    fatalities = EXCLUDED.fatalities,
    tags = EXCLUDED.tags,
    timestamp = EXCLUDED.timestamp,
    population_best = EXCLUDED.population_best,
    population_1km = EXCLUDED.population_1km,
    population_2km = EXCLUDED.population_2km,
    population_5km = EXCLUDED.population_5km,
    geom = EXCLUDED.geom
"""


class Database:
    def __init__(self, settings: IngestSettings) -> None:
        self._settings = settings

    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection[Any]]:
        with psycopg.connect(self._settings.conninfo) as conn:
            yield conn

    def upsert_events(self, events: Sequence[tuple[Any, ...]]) -> int:
        if not events:
            return 0
        with self.connection() as conn, conn.cursor() as cursor:
            cursor.executemany(UPSERT_SQL, events)
            conn.commit()
        return len(events)

    def create_ingestion_log(
        self,
        *,
        phase: str,
        status: str,
        started_at: datetime | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        last_timestamp: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        started_at = started_at or datetime.now(timezone.utc)
        with self.connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO ingestion_log (
                    phase, started_at, status, date_from, date_to, last_timestamp, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id
                """,
                (
                    phase,
                    started_at,
                    status,
                    date_from,
                    date_to,
                    last_timestamp,
                    json.dumps(metadata or {}),
                ),
            )
            log_id = int(cursor.fetchone()[0])
            conn.commit()
        return log_id

    def complete_ingestion_log(
        self,
        log_id: int,
        *,
        status: str,
        events_upserted: int,
        error_message: str | None = None,
        last_timestamp: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self.connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE ingestion_log
                SET completed_at = %s,
                    status = %s,
                    events_upserted = %s,
                    error_message = %s,
                    last_timestamp = COALESCE(%s, last_timestamp),
                    metadata = COALESCE(%s::jsonb, metadata)
                WHERE id = %s
                """,
                (
                    datetime.now(timezone.utc),
                    status,
                    events_upserted,
                    error_message,
                    last_timestamp,
                    json.dumps(metadata) if metadata is not None else None,
                    log_id,
                ),
            )
            conn.commit()

    def get_last_successful_timestamp(self) -> int | None:
        with self.connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT last_timestamp
                FROM ingestion_log
                WHERE status = 'success' AND last_timestamp IS NOT NULL
                ORDER BY completed_at DESC NULLS LAST, started_at DESC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
        if not row:
            return None
        return row["last_timestamp"]

    def create_user(self, *, username: str, password: str, display_name: str | None = None) -> None:
        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        with self.connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO users (username, password_hash, display_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (username) DO UPDATE
                SET password_hash = EXCLUDED.password_hash,
                    display_name = EXCLUDED.display_name,
                    is_active = TRUE
                """,
                (username, password_hash, display_name),
            )
            conn.commit()


def chunked(items: Sequence[tuple[Any, ...]], size: int) -> Iterable[Sequence[tuple[Any, ...]]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]

