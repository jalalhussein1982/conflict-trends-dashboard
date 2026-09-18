"""MCP server over the Sahel Information Environment Monitor.

    siem-mcp                                   # stdio, synthetic events (no ACLED data)
    uv run mcp dev src/siem_mcp/server.py      # MCP Inspector
    SIEM_MODE=live SIEM_DB_HOST=... siem-mcp   # stdio over the live PostGIS database

Tools answer the questions an analyst asks of the map: how many events, how lethal, who, where,
what is near a point, and whether the data is fresh. Resources give the agent the schema, the
coverage and the event taxonomy without a tool call. One prompt turns a window into a brief.

Choices, stated once:

* One ``Store`` interface, two backends (synthetic SQLite, live PostGIS). The MCP layer does not
  know which one it has; ``coverage`` says so in its ``mode`` field.
* Aggregates first. Event-level tools are capped and never return ACLED's ``notes`` or ``source``
  text; in live mode this server serves an authenticated operator what the dashboard already
  serves, and redistributes nothing.
* ``ToolError`` for a window the model can fix (end before start, unknown country, too wide);
  a database failure is a crash, sanitised by the SDK, logged on the server.
* Read-only. No tool writes.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import synth
from .store import Granularity, Store, Window, open_store

MAX_WINDOW_DAYS = 366 * 10
COUNTRIES = tuple(synth.REGIONS)  # the monitor's scope: Mali, Burkina Faso, Niger

mcp = MCPServer(
    "siem",
    instructions=(
        "Conflict-event analytics for the Sahel (Mali, Burkina Faso, Niger). Start with coverage to learn "
        "the date range and mode (synthetic or live). Prefer aggregate tools (event_counts, lethality, "
        "top_actors, event_type_mix, admin1_summary) and use event-level tools (events_in_bbox, events_near) "
        "only to inspect specific places. Dates are ISO (YYYY-MM-DD)."
    ),
)

_store: Store | None = None


def store() -> Store:
    global _store
    if _store is None:
        _store = open_store()
    return _store


def use_store(s: Store) -> None:
    """Swap the backend (tests, or a host that builds the store itself)."""
    global _store
    _store = s


# ── output models ────────────────────────────────────────────────────────────────────


class CountryCoverage(BaseModel):
    country: str
    events: int
    fatalities: int


class Coverage(BaseModel):
    mode: Literal["synthetic", "live"] = Field(description="synthetic: bundled generated events; live: the PostGIS database.")
    events: int
    date_start: str
    date_end: str
    fatalities: int
    countries: list[CountryCoverage]


class PeriodRow(BaseModel):
    period: str
    events: int
    fatalities: int
    fatalities_per_event: float | None = None


class ActorRow(BaseModel):
    actor: str
    events: int
    fatalities: int


class TypeRow(BaseModel):
    event_type: str
    sub_event_type: str | None
    events: int
    fatalities: int
    civilian_targeting: int = Field(description="Events in this type flagged as civilian targeting.")


class Admin1Row(BaseModel):
    country: str
    admin1: str
    events: int
    fatalities: int


class EventRow(BaseModel):
    event_id_cnty: str
    event_date: str
    event_type: str
    sub_event_type: str | None
    actor1: str | None
    actor2: str | None
    country: str
    admin1: str | None
    location: str | None
    latitude: float | None
    longitude: float | None
    fatalities: int
    civilian_targeting: str | None
    distance_km: float | None = None


class IngestionRow(BaseModel):
    id: int
    phase: str
    started_at: str
    completed_at: str | None
    status: str
    events_upserted: int | None
    date_from: str | None
    date_to: str | None
    last_timestamp: int | None
    error_message: str | None


# ── argument handling ────────────────────────────────────────────────────────────────

DateArg = Annotated[str, Field(description="ISO date, YYYY-MM-DD.")]
CountryArg = Annotated[str | None, Field(description="Mali, Burkina Faso or Niger. Omit for all three.")]
TypesArg = Annotated[list[str] | None, Field(description="ACLED event types to keep, e.g. ['Battles']. Omit for all.")]


def _window(date_start: str, date_end: str, country: str | None, event_types: list[str] | None) -> Window:
    try:
        a, b = date.fromisoformat(date_start), date.fromisoformat(date_end)
    except ValueError as e:
        raise ToolError(f"Dates must be ISO YYYY-MM-DD: {e}")
    if b < a:
        raise ToolError(f"date_end {date_end} is before date_start {date_start}.")
    if (b - a) > timedelta(days=MAX_WINDOW_DAYS):
        raise ToolError(f"Window is wider than {MAX_WINDOW_DAYS} days; narrow it or use granularity='year' on a shorter span.")
    if country is not None and country not in COUNTRIES:
        raise ToolError(f"Unknown country {country!r}. This monitor covers: {', '.join(COUNTRIES)}.")
    if event_types:
        bad = [t for t in event_types if t not in synth.EVENT_TYPES]
        if bad:
            raise ToolError(f"Unknown event types {bad}. Known: {', '.join(synth.EVENT_TYPES)}.")
    return Window(a, b, country, tuple(event_types or ()))


# ── tools ────────────────────────────────────────────────────────────────────────────


@mcp.tool()
def coverage() -> Coverage:
    """What the monitor holds: mode (synthetic or live), event count, date range, fatalities, per-country totals.

    Call this first; it tells you the date range every other tool can be asked about."""
    return Coverage(**store().coverage())


@mcp.tool()
def event_counts(
    date_start: DateArg,
    date_end: DateArg,
    country: CountryArg = None,
    event_types: TypesArg = None,
    granularity: Annotated[Granularity, Field(description="Bucket size for the series.")] = "month",
) -> list[PeriodRow]:
    """Event and fatality counts per period over a date window. The basic trend line."""
    w = _window(date_start, date_end, country, event_types)
    return [PeriodRow(**r) for r in store().event_counts(w, granularity)]


@mcp.tool()
def lethality(
    date_start: DateArg,
    date_end: DateArg,
    country: CountryArg = None,
    event_types: TypesArg = None,
    granularity: Annotated[Granularity, Field(description="Bucket size for the series.")] = "quarter",
) -> list[PeriodRow]:
    """Fatalities per event over time: are events getting deadlier, not just more frequent?"""
    w = _window(date_start, date_end, country, event_types)
    return [PeriodRow(**r) for r in store().lethality(w, granularity)]


@mcp.tool()
def top_actors(
    date_start: DateArg,
    date_end: DateArg,
    country: CountryArg = None,
    event_types: TypesArg = None,
    role: Annotated[Literal["actor1", "actor2", "both"], Field(description="Which actor column to count.")] = "both",
    limit: Annotated[int, Field(ge=1, le=50)] = 10,
) -> list[ActorRow]:
    """Actor composition: which actors appear most in the window, with the fatalities of their events."""
    w = _window(date_start, date_end, country, event_types)
    return [ActorRow(**r) for r in store().top_actors(w, role, limit)]


@mcp.tool()
def event_type_mix(
    date_start: DateArg,
    date_end: DateArg,
    country: CountryArg = None,
) -> list[TypeRow]:
    """Breakdown by event type and sub-type, with the civilian-targeting count per type."""
    w = _window(date_start, date_end, country, None)
    return [TypeRow(**r) for r in store().event_type_mix(w)]


@mcp.tool()
def admin1_summary(
    date_start: DateArg,
    date_end: DateArg,
    country: CountryArg = None,
    event_types: TypesArg = None,
    limit: Annotated[int, Field(ge=1, le=50)] = 15,
) -> list[Admin1Row]:
    """Hotspots by first-level administrative region, most events first."""
    w = _window(date_start, date_end, country, event_types)
    return [Admin1Row(**r) for r in store().admin1_summary(w, limit)]


@mcp.tool()
def events_in_bbox(
    date_start: DateArg,
    date_end: DateArg,
    west: Annotated[float, Field(ge=-180, le=180)],
    south: Annotated[float, Field(ge=-90, le=90)],
    east: Annotated[float, Field(ge=-180, le=180)],
    north: Annotated[float, Field(ge=-90, le=90)],
    event_types: TypesArg = None,
    limit: Annotated[int, Field(ge=1, le=200)] = 50,
) -> list[EventRow]:
    """Events inside a bounding box (the same query the map runs), newest first, capped."""
    if east <= west or north <= south:
        raise ToolError("Bounding box must have west < east and south < north.")
    w = _window(date_start, date_end, None, event_types)
    return [EventRow(**r) for r in store().events_in_bbox(w, (west, south, east, north), limit)]


@mcp.tool()
def events_near(
    date_start: DateArg,
    date_end: DateArg,
    latitude: Annotated[float, Field(ge=-90, le=90)],
    longitude: Annotated[float, Field(ge=-180, le=180)],
    radius_km: Annotated[float, Field(gt=0, le=500)] = 50,
    event_types: TypesArg = None,
    limit: Annotated[int, Field(ge=1, le=200)] = 50,
) -> list[EventRow]:
    """Events within a radius of a point, nearest first, with the distance in km."""
    w = _window(date_start, date_end, None, event_types)
    return [EventRow(**r) for r in store().events_near(w, latitude, longitude, radius_km, limit)]


@mcp.tool()
def ingestion_status(limit: Annotated[int, Field(ge=1, le=50)] = 5) -> list[IngestionRow]:
    """Recent ingestion runs (bulk load, daily CronJob): status, rows upserted, date window, last ACLED timestamp.

    Use it to say how fresh the data is before drawing a trend to 'present'."""
    return [IngestionRow(**r) for r in store().ingestion_status(limit)]


# ── resources ────────────────────────────────────────────────────────────────────────

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "deploy" / "sql" / "schema.sql"


@mcp.resource("siem://schema", mime_type="text/x-sql")
def schema() -> str:
    """The acled_events / ingestion_log DDL the live database runs on."""
    if SCHEMA_PATH.is_file():
        return SCHEMA_PATH.read_text(encoding="utf-8")
    return "-- schema.sql not found next to this package; see phase1/deploy/sql/schema.sql in the repository"


@mcp.resource("siem://coverage", mime_type="application/json")
def coverage_resource() -> dict[str, Any]:
    """Same as the coverage tool, as a document."""
    return store().coverage()


@mcp.resource("siem://event-types", mime_type="application/json")
def event_types_resource() -> dict[str, list[str]]:
    """ACLED event types and sub-types the tools accept."""
    return synth.EVENT_TYPES


# ── prompt ───────────────────────────────────────────────────────────────────────────


@mcp.prompt(title="Situation brief for a window")
def situation_brief(
    country: Annotated[str, Field(description="Mali, Burkina Faso or Niger.")],
    date_start: DateArg,
    date_end: DateArg,
) -> str:
    """Ask the model to build a short evidence-first brief from the tools, not from memory."""
    return (
        f"Build a situation brief for {country} from {date_start} to {date_end} using only this server's tools. "
        "Call coverage and ingestion_status first and state the data's freshness and mode. Then event_counts "
        "(monthly), lethality (quarterly), event_type_mix, top_actors and admin1_summary. Write five short "
        "paragraphs: trend, lethality, who, where, and what the data cannot tell you. Give numbers with their "
        "period. Do not add facts the tools did not return."
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
