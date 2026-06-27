from __future__ import annotations

from datetime import date
from typing import Any, Mapping


def _as_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _as_int(value: Any, *, default: int | None = None) -> int | None:
    if value in (None, ""):
        return default
    return int(value)


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def normalize_event(raw_event: Mapping[str, Any]) -> tuple[Any, ...]:
    latitude = _as_float(raw_event.get("latitude"))
    longitude = _as_float(raw_event.get("longitude"))
    return (
        raw_event["event_id_cnty"],
        _as_date(raw_event["event_date"]),
        int(raw_event["year"]),
        _as_int(raw_event.get("time_precision")),
        raw_event.get("disorder_type"),
        raw_event.get("event_type"),
        raw_event.get("sub_event_type"),
        raw_event.get("actor1"),
        raw_event.get("assoc_actor_1"),
        raw_event.get("inter1"),
        raw_event.get("actor2"),
        raw_event.get("assoc_actor_2"),
        raw_event.get("inter2"),
        raw_event.get("interaction"),
        raw_event.get("civilian_targeting"),
        _as_int(raw_event.get("iso")),
        raw_event.get("region"),
        raw_event.get("country"),
        raw_event.get("admin1"),
        raw_event.get("admin2"),
        raw_event.get("admin3"),
        raw_event.get("location"),
        latitude,
        longitude,
        _as_int(raw_event.get("geo_precision")),
        raw_event.get("source"),
        raw_event.get("source_scale"),
        raw_event.get("notes"),
        _as_int(raw_event.get("fatalities"), default=0),
        raw_event.get("tags"),
        _as_int(raw_event.get("timestamp")),
        _as_int(raw_event.get("population_best")),
        _as_int(raw_event.get("population_1km")),
        _as_int(raw_event.get("population_2km")),
        _as_int(raw_event.get("population_5km")),
        longitude,
        latitude,
    )

