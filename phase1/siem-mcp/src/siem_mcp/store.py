"""Two stores, one interface.

``SqliteStore`` loads the synthetic events into an in-memory SQLite database at start-up and
answers every query with plain SQL plus a haversine distance for the spatial tool.
``PostgresStore`` runs the same queries against the live ``acled_events`` table with PostGIS
for the spatial parts. The MCP layer never sees which one it has.

Neither store returns the ``notes`` or ``source`` columns. In live mode those are ACLED's text
and this server does not redistribute it; the aggregates and the minimal event fields are what
the dashboard already serves to an authenticated operator.
"""

from __future__ import annotations

import math
import os
import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, Protocol

from . import synth

Granularity = Literal["year", "quarter", "month", "week"]

EVENT_FIELDS = ("event_id_cnty", "event_date", "event_type", "sub_event_type", "actor1", "actor2",
                "country", "admin1", "location", "latitude", "longitude", "fatalities", "civilian_targeting")


@dataclass(frozen=True)
class Window:
    date_start: date
    date_end: date
    country: str | None = None
    event_types: tuple[str, ...] = ()


class Store(Protocol):
    mode: str

    def coverage(self) -> dict[str, Any]: ...
    def event_counts(self, w: Window, granularity: Granularity) -> list[dict[str, Any]]: ...
    def lethality(self, w: Window, granularity: Granularity) -> list[dict[str, Any]]: ...
    def top_actors(self, w: Window, role: Literal["actor1", "actor2", "both"], limit: int) -> list[dict[str, Any]]: ...
    def event_type_mix(self, w: Window) -> list[dict[str, Any]]: ...
    def admin1_summary(self, w: Window, limit: int) -> list[dict[str, Any]]: ...
    def events_in_bbox(self, w: Window, bbox: tuple[float, float, float, float], limit: int) -> list[dict[str, Any]]: ...
    def events_near(self, w: Window, lat: float, lon: float, radius_km: float, limit: int) -> list[dict[str, Any]]: ...
    def ingestion_status(self, limit: int) -> list[dict[str, Any]]: ...


# ── helpers shared by both stores ────────────────────────────────────────────────────


def period_sql(granularity: Granularity, dialect: Literal["sqlite", "postgres"]) -> str:
    if dialect == "sqlite":
        return {
            "year": "strftime('%Y', event_date)",
            "quarter": "strftime('%Y', event_date) || '-Q' || ((cast(strftime('%m', event_date) as integer) + 2) / 3)",
            "month": "strftime('%Y-%m', event_date)",
            "week": "strftime('%Y-W%W', event_date)",
        }[granularity]
    return {
        "year": "to_char(event_date, 'YYYY')",
        "quarter": "to_char(event_date, 'YYYY-\"Q\"Q')",
        "month": "to_char(event_date, 'YYYY-MM')",
        "week": "to_char(event_date, 'IYYY-\"W\"IW')",
    }[granularity]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# ── SQLite (synthetic) ───────────────────────────────────────────────────────────────


class SqliteStore:
    mode = "synthetic"

    def __init__(self, events: list[dict] | None = None) -> None:
        self._db = sqlite3.connect(":memory:", check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        cols = list(synth.generate(1)[0].keys())
        self._db.execute(f"CREATE TABLE acled_events ({', '.join(cols)})")
        self._db.execute(
            "CREATE TABLE ingestion_log (id INTEGER PRIMARY KEY, phase TEXT, started_at TEXT, completed_at TEXT, "
            "status TEXT, events_upserted INTEGER, date_from TEXT, date_to TEXT, last_timestamp INTEGER, error_message TEXT)"
        )
        rows = events if events is not None else synth.generate()
        self._db.executemany(
            f"INSERT INTO acled_events ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
            [tuple(e[c] for c in cols) for e in rows],
        )
        first, last = rows[0]["event_date"], rows[-1]["event_date"]
        self._db.execute(
            "INSERT INTO ingestion_log VALUES (1,'bulk','2026-09-01T00:05:00Z','2026-09-01T00:09:12Z','success',?,?,?,?,NULL)",
            (len(rows), first, last, rows[-1]["timestamp"]),
        )
        self._db.execute(
            "INSERT INTO ingestion_log VALUES (2,'daily','2026-09-18T00:05:00Z','2026-09-18T00:05:41Z','success',0,?,?,?,NULL)",
            (last, last, rows[-1]["timestamp"]),
        )
        self._db.commit()

    # -- query building ----------------------------------------------------------------

    def _where(self, w: Window) -> tuple[str, list[Any]]:
        parts, params = ["event_date BETWEEN ? AND ?"], [w.date_start.isoformat(), w.date_end.isoformat()]
        if w.country:
            parts.append("country = ?"); params.append(w.country)
        if w.event_types:
            parts.append(f"event_type IN ({', '.join('?' for _ in w.event_types)})"); params.extend(w.event_types)
        return " AND ".join(parts), params

    def _rows(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        return [dict(r) for r in self._db.execute(sql, params).fetchall()]

    # -- interface ---------------------------------------------------------------------

    def coverage(self) -> dict[str, Any]:
        tot = self._db.execute("SELECT count(*) n, min(event_date) a, max(event_date) b, sum(fatalities) f FROM acled_events").fetchone()
        by_c = self._rows("SELECT country, count(*) events, sum(fatalities) fatalities FROM acled_events GROUP BY country ORDER BY country", [])
        return {"mode": self.mode, "events": tot["n"], "date_start": tot["a"], "date_end": tot["b"],
                "fatalities": tot["f"], "countries": by_c}

    def event_counts(self, w: Window, granularity: Granularity) -> list[dict[str, Any]]:
        where, params = self._where(w)
        p = period_sql(granularity, "sqlite")
        return self._rows(f"SELECT {p} period, count(*) events, sum(fatalities) fatalities FROM acled_events "
                          f"WHERE {where} GROUP BY period ORDER BY period", params)

    def lethality(self, w: Window, granularity: Granularity) -> list[dict[str, Any]]:
        rows = self.event_counts(w, granularity)
        for r in rows:
            r["fatalities_per_event"] = round(r["fatalities"] / r["events"], 2) if r["events"] else 0.0
        return rows

    def top_actors(self, w: Window, role: Literal["actor1", "actor2", "both"], limit: int) -> list[dict[str, Any]]:
        where, params = self._where(w)
        if role == "both":
            sql = (f"SELECT actor, count(*) events, sum(fatalities) fatalities FROM ("
                   f"SELECT actor1 actor, fatalities FROM acled_events WHERE {where} AND actor1 IS NOT NULL "
                   f"UNION ALL SELECT actor2, fatalities FROM acled_events WHERE {where} AND actor2 IS NOT NULL) "
                   f"GROUP BY actor ORDER BY events DESC, actor LIMIT ?")
            return self._rows(sql, params + params + [limit])
        return self._rows(f"SELECT {role} actor, count(*) events, sum(fatalities) fatalities FROM acled_events "
                          f"WHERE {where} AND {role} IS NOT NULL GROUP BY actor ORDER BY events DESC, actor LIMIT ?",
                          params + [limit])

    def event_type_mix(self, w: Window) -> list[dict[str, Any]]:
        where, params = self._where(w)
        return self._rows(f"SELECT event_type, sub_event_type, count(*) events, sum(fatalities) fatalities, "
                          f"sum(CASE WHEN civilian_targeting IS NOT NULL THEN 1 ELSE 0 END) civilian_targeting "
                          f"FROM acled_events WHERE {where} GROUP BY event_type, sub_event_type ORDER BY events DESC", params)

    def admin1_summary(self, w: Window, limit: int) -> list[dict[str, Any]]:
        where, params = self._where(w)
        return self._rows(f"SELECT country, admin1, count(*) events, sum(fatalities) fatalities "
                          f"FROM acled_events WHERE {where} GROUP BY country, admin1 ORDER BY events DESC, admin1 LIMIT ?",
                          params + [limit])

    def events_in_bbox(self, w: Window, bbox: tuple[float, float, float, float], limit: int) -> list[dict[str, Any]]:
        where, params = self._where(w)
        west, south, east, north = bbox
        return self._rows(f"SELECT {', '.join(EVENT_FIELDS)} FROM acled_events WHERE {where} "
                          f"AND longitude BETWEEN ? AND ? AND latitude BETWEEN ? AND ? ORDER BY event_date DESC LIMIT ?",
                          params + [west, east, south, north, limit])

    def events_near(self, w: Window, lat: float, lon: float, radius_km: float, limit: int) -> list[dict[str, Any]]:
        where, params = self._where(w)
        dlat = radius_km / 111.0
        dlon = radius_km / (111.0 * max(0.1, math.cos(math.radians(lat))))
        cand = self._rows(f"SELECT {', '.join(EVENT_FIELDS)} FROM acled_events WHERE {where} "
                          f"AND latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?",
                          params + [lat - dlat, lat + dlat, lon - dlon, lon + dlon])
        for r in cand:
            r["distance_km"] = round(haversine_km(lat, lon, r["latitude"], r["longitude"]), 1)
        cand = [r for r in cand if r["distance_km"] <= radius_km]
        cand.sort(key=lambda r: (r["distance_km"], r["event_date"]))
        return cand[:limit]

    def ingestion_status(self, limit: int) -> list[dict[str, Any]]:
        return self._rows("SELECT id, phase, started_at, completed_at, status, events_upserted, date_from, date_to, "
                          "last_timestamp, error_message FROM ingestion_log ORDER BY started_at DESC LIMIT ?", [limit])


# ── PostgreSQL / PostGIS (live) ──────────────────────────────────────────────────────


class PostgresStore:
    """Same queries against the live schema. Requires ``psycopg`` and SIEM_DB_* / DB_* env vars."""

    mode = "live"

    def __init__(self, conninfo: str) -> None:
        import psycopg  # optional dependency, imported here on purpose
        from psycopg.rows import dict_row

        self._psycopg = psycopg
        self._conn = psycopg.connect(conninfo, row_factory=dict_row, autocommit=True)

    @classmethod
    def from_env(cls) -> "PostgresStore":
        from psycopg.conninfo import make_conninfo

        def env(name: str) -> str | None:
            return os.getenv(f"SIEM_{name}") or os.getenv(name)

        missing = [n for n in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD") if not env(n)]
        if missing:
            raise RuntimeError(f"live mode needs {', '.join(missing)}")
        return cls(make_conninfo(host=env("DB_HOST"), port=int(env("DB_PORT")), dbname=env("DB_NAME"),
                                 user=env("DB_USER"), password=env("DB_PASSWORD")))

    def _where(self, w: Window) -> tuple[str, list[Any]]:
        parts, params = ["event_date BETWEEN %s AND %s"], [w.date_start, w.date_end]
        if w.country:
            parts.append("country = %s"); params.append(w.country)
        if w.event_types:
            parts.append("event_type = ANY(%s::text[])"); params.append(list(w.event_types))
        return " AND ".join(parts), params

    def _rows(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            out = []
            for r in cur.fetchall():
                out.append({k: (v.isoformat() if isinstance(v, date) else v) for k, v in r.items()})
            return out

    def coverage(self) -> dict[str, Any]:
        tot = self._rows("SELECT count(*) n, min(event_date) a, max(event_date) b, coalesce(sum(fatalities),0) f FROM acled_events", [])[0]
        by_c = self._rows("SELECT country, count(*) events, coalesce(sum(fatalities),0) fatalities FROM acled_events GROUP BY country ORDER BY country", [])
        return {"mode": self.mode, "events": tot["n"], "date_start": tot["a"], "date_end": tot["b"], "fatalities": tot["f"], "countries": by_c}

    def event_counts(self, w: Window, granularity: Granularity) -> list[dict[str, Any]]:
        where, params = self._where(w)
        p = period_sql(granularity, "postgres")
        return self._rows(f"SELECT {p} period, count(*) events, coalesce(sum(fatalities),0) fatalities FROM acled_events "
                          f"WHERE {where} GROUP BY 1 ORDER BY 1", params)

    def lethality(self, w: Window, granularity: Granularity) -> list[dict[str, Any]]:
        rows = self.event_counts(w, granularity)
        for r in rows:
            r["fatalities_per_event"] = round(r["fatalities"] / r["events"], 2) if r["events"] else 0.0
        return rows

    def top_actors(self, w: Window, role: Literal["actor1", "actor2", "both"], limit: int) -> list[dict[str, Any]]:
        where, params = self._where(w)
        if role == "both":
            sql = (f"SELECT actor, count(*) events, coalesce(sum(fatalities),0) fatalities FROM ("
                   f"SELECT actor1 actor, fatalities FROM acled_events WHERE {where} AND actor1 IS NOT NULL "
                   f"UNION ALL SELECT actor2, fatalities FROM acled_events WHERE {where} AND actor2 IS NOT NULL) u "
                   f"GROUP BY actor ORDER BY events DESC, actor LIMIT %s")
            return self._rows(sql, params + params + [limit])
        col = "actor1" if role == "actor1" else "actor2"
        return self._rows(f"SELECT {col} actor, count(*) events, coalesce(sum(fatalities),0) fatalities FROM acled_events "
                          f"WHERE {where} AND {col} IS NOT NULL GROUP BY 1 ORDER BY events DESC, actor LIMIT %s", params + [limit])

    def event_type_mix(self, w: Window) -> list[dict[str, Any]]:
        where, params = self._where(w)
        return self._rows(f"SELECT event_type, sub_event_type, count(*) events, coalesce(sum(fatalities),0) fatalities, "
                          f"count(civilian_targeting) civilian_targeting FROM acled_events WHERE {where} "
                          f"GROUP BY 1, 2 ORDER BY events DESC", params)

    def admin1_summary(self, w: Window, limit: int) -> list[dict[str, Any]]:
        where, params = self._where(w)
        return self._rows(f"SELECT country, admin1, count(*) events, coalesce(sum(fatalities),0) fatalities FROM acled_events "
                          f"WHERE {where} GROUP BY 1, 2 ORDER BY events DESC, admin1 LIMIT %s", params + [limit])

    def events_in_bbox(self, w: Window, bbox: tuple[float, float, float, float], limit: int) -> list[dict[str, Any]]:
        where, params = self._where(w)
        west, south, east, north = bbox
        return self._rows(f"SELECT {', '.join(EVENT_FIELDS)} FROM acled_events WHERE {where} "
                          f"AND geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326) ORDER BY event_date DESC LIMIT %s",
                          params + [west, south, east, north, limit])

    def events_near(self, w: Window, lat: float, lon: float, radius_km: float, limit: int) -> list[dict[str, Any]]:
        where, params = self._where(w)
        return self._rows(
            f"SELECT {', '.join(EVENT_FIELDS)}, round((ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography) / 1000)::numeric, 1) distance_km "
            f"FROM acled_events WHERE {where} AND ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s) "
            f"ORDER BY distance_km, event_date LIMIT %s",
            [lon, lat] + params + [lon, lat, radius_km * 1000, limit])

    def ingestion_status(self, limit: int) -> list[dict[str, Any]]:
        return self._rows("SELECT id, phase, started_at, completed_at, status, events_upserted, date_from, date_to, "
                          "last_timestamp, error_message FROM ingestion_log ORDER BY started_at DESC LIMIT %s", [limit])


def open_store() -> Store:
    """Live PostGIS when SIEM_MODE=live (or DB vars are set and SIEM_MODE is unset), else synthetic."""
    mode = os.getenv("SIEM_MODE", "").lower()
    has_db = bool(os.getenv("SIEM_DB_HOST") or os.getenv("DB_HOST"))
    if mode == "live" or (mode == "" and has_db):
        return PostgresStore.from_env()
    return SqliteStore()
