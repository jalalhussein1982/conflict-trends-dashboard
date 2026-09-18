# siem-mcp

An MCP server over the Sahel Information Environment Monitor. It gives an agent the questions an
analyst asks of the map, as tools with typed results: how many events, how lethal, who, where,
what is near a point, and whether the data is fresh.

Built September 2026 with the MCP Python SDK 2.x against protocol revision 2026-07-28.

## Tools, resources, prompt

| Tool | Answers |
|---|---|
| `coverage` | what is loaded: mode (synthetic or live), event count, date range, per-country totals |
| `event_counts` | events and fatalities per year / quarter / month / week, filtered by country and event type |
| `lethality` | fatalities per event over time |
| `top_actors` | actor composition in a window (actor1, actor2 or both) |
| `event_type_mix` | breakdown by ACLED event type and sub-type, with civilian-targeting counts |
| `admin1_summary` | hotspots by first-level administrative region |
| `events_in_bbox` | the map's own query: events inside a bounding box, capped |
| `events_near` | events within a radius of a point, nearest first, with distance in km |
| `ingestion_status` | recent bulk and daily ingestion runs, so "present" has a date on it |

Resources: `siem://schema` (the live DDL), `siem://coverage`, `siem://event-types`.
Prompt: `situation_brief(country, date_start, date_end)`, which tells the model to build the brief
from the tools and to say what the data cannot show.

## Run it

```bash
cd phase1/siem-mcp
uv venv && uv pip install -e ".[test]"
.venv/bin/pytest                               # 12 in-memory protocol tests
.venv/bin/mcp dev src/siem_mcp/server.py       # MCP Inspector over stdio
.venv/bin/siem-mcp                             # stdio, for a host
```

With no configuration the server runs on **synthetic events**: 6 000 generated records with the
`acled_events` columns, ACLED's public event taxonomy, real first-level regions and invented actors.
**No ACLED data is redistributed in this repository.**

Against the live database (`.env.example` lists the variables):

```bash
uv pip install -e ".[postgres]"
SIEM_MODE=live SIEM_DB_HOST=... SIEM_DB_PORT=5432 SIEM_DB_NAME=siem SIEM_DB_USER=... SIEM_DB_PASSWORD=... .venv/bin/siem-mcp
```

`.mcp.json` in this folder registers the server for Claude Code when the session starts here.

## Design decisions

**One interface, two stores.** `store.py` defines the queries once as a protocol. `SqliteStore`
loads the synthetic events into memory and answers with plain SQL plus a haversine distance.
`PostgresStore` runs the same queries on the live `acled_events` table with PostGIS
(`ST_MakeEnvelope`, `ST_DWithin` on geography). The MCP layer does not know which one it has;
`coverage.mode` says.

**Aggregates first, event rows capped, no text columns.** The event-level tools return the
minimal fields the dashboard shows and never `notes` or `source`. In live mode the server serves an
authenticated operator what the map already serves, and caches or redistributes nothing. A test
asserts the two columns are absent.

**Errors the model can fix are `ToolError`.** A window with the end before the start, a country
outside the monitor's scope, an unknown event type, a ten-year span: the model reads the message
and retries. A database failure is a crash; the SDK sanitises it for the caller and logs it here.

**Pydantic return types are the output schemas.** `structured_content` matches them, so a host
application reads numbers as numbers; the model reads the same rows as text.

**Deterministic tool order and read-only.** Nothing writes. The tool list is fixed so hosts can
cache it, as the 2026-07-28 revision asks.

## What it is not

The live store has been written against the schema in `deploy/sql/schema.sql` and exercised only
through the synthetic store's identical interface; it has not been run against a populated PostGIS
in this repository. There is no HTTP deployment and no authorization layer; stdio under an
operator's own credentials is the intended use.
