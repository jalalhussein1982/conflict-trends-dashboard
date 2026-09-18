"""In-memory protocol tests over the synthetic store."""

from __future__ import annotations

import json

import pytest

from mcp import Client

from siem_mcp.server import mcp, use_store
from siem_mcp.store import SqliteStore, haversine_km


@pytest.fixture(scope="module")
def synthetic_store():
    return SqliteStore()


@pytest.fixture(autouse=True)
def _use_synthetic(synthetic_store):
    use_store(synthetic_store)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with Client(mcp, raise_exceptions=True) as c:
        yield c


@pytest.mark.anyio
async def test_tool_order_is_fixed(client: Client):
    names = [t.name for t in (await client.list_tools()).tools]
    assert names == ["coverage", "event_counts", "lethality", "top_actors", "event_type_mix",
                     "admin1_summary", "events_in_bbox", "events_near", "ingestion_status"]


@pytest.mark.anyio
async def test_coverage_is_synthetic_and_adds_up(client: Client):
    c = (await client.call_tool("coverage", {})).structured_content
    assert c["mode"] == "synthetic"
    assert c["events"] == sum(x["events"] for x in c["countries"]) == 6000
    assert {x["country"] for x in c["countries"]} == {"Mali", "Burkina Faso", "Niger"}


@pytest.mark.anyio
async def test_event_counts_sum_to_coverage_over_the_full_range(client: Client):
    c = (await client.call_tool("coverage", {})).structured_content
    rows = (await client.call_tool("event_counts", {"date_start": c["date_start"], "date_end": c["date_end"],
                                                    "granularity": "year"})).structured_content["result"]
    assert sum(r["events"] for r in rows) == c["events"]
    assert [r["period"] for r in rows] == sorted(r["period"] for r in rows)


@pytest.mark.anyio
async def test_country_filter_matches_coverage(client: Client):
    c = (await client.call_tool("coverage", {})).structured_content
    mali = next(x for x in c["countries"] if x["country"] == "Mali")
    rows = (await client.call_tool("event_counts", {"date_start": c["date_start"], "date_end": c["date_end"],
                                                    "country": "Mali", "granularity": "year"})).structured_content["result"]
    assert sum(r["events"] for r in rows) == mali["events"]


@pytest.mark.anyio
async def test_top_actors_is_sorted_and_capped(client: Client):
    rows = (await client.call_tool("top_actors", {"date_start": "2024-01-01", "date_end": "2024-12-31",
                                                  "limit": 5})).structured_content["result"]
    assert len(rows) == 5
    assert [r["events"] for r in rows] == sorted((r["events"] for r in rows), reverse=True)


@pytest.mark.anyio
async def test_events_near_respects_radius_and_orders_by_distance(client: Client):
    lat, lon = 16.27, -0.04  # Gao centroid
    rows = (await client.call_tool("events_near", {"date_start": "2020-01-01", "date_end": "2026-12-31",
                                                   "latitude": lat, "longitude": lon, "radius_km": 40,
                                                   "limit": 100})).structured_content["result"]
    assert rows
    assert all(r["distance_km"] <= 40 for r in rows)
    assert [r["distance_km"] for r in rows] == sorted(r["distance_km"] for r in rows)
    r0 = rows[0]
    assert abs(haversine_km(lat, lon, r0["latitude"], r0["longitude"]) - r0["distance_km"]) < 0.1


@pytest.mark.anyio
async def test_bbox_filters_coordinates(client: Client):
    rows = (await client.call_tool("events_in_bbox", {"date_start": "2023-01-01", "date_end": "2023-12-31",
                                                      "west": 0.0, "south": 13.0, "east": 3.0, "north": 15.0,
                                                      "limit": 200})).structured_content["result"]
    assert rows
    assert all(0.0 <= r["longitude"] <= 3.0 and 13.0 <= r["latitude"] <= 15.0 for r in rows)


@pytest.mark.anyio
async def test_event_rows_never_carry_notes_or_source(client: Client):
    rows = (await client.call_tool("events_in_bbox", {"date_start": "2023-01-01", "date_end": "2023-12-31",
                                                      "west": -12.0, "south": 10.0, "east": 16.0, "north": 24.0,
                                                      "limit": 5})).structured_content["result"]
    for r in rows:
        assert "notes" not in r and "source" not in r


@pytest.mark.anyio
async def test_bad_windows_are_tool_errors(client: Client):
    r = await client.call_tool("event_counts", {"date_start": "2024-06-01", "date_end": "2024-01-01"})
    assert r.is_error and "before" in r.content[0].text
    r = await client.call_tool("event_counts", {"date_start": "2024-01-01", "date_end": "2024-02-01", "country": "Chad"})
    assert r.is_error and "Mali" in r.content[0].text
    r = await client.call_tool("event_counts", {"date_start": "2010-01-01", "date_end": "2026-01-01"})
    assert r.is_error and "wider" in r.content[0].text


@pytest.mark.anyio
async def test_schema_validation_rejects_bad_radius(client: Client):
    r = await client.call_tool("events_near", {"date_start": "2024-01-01", "date_end": "2024-02-01",
                                               "latitude": 16.0, "longitude": 0.0, "radius_km": 5000})
    assert r.is_error


@pytest.mark.anyio
async def test_ingestion_status_reports_freshness(client: Client):
    rows = (await client.call_tool("ingestion_status", {})).structured_content["result"]
    assert rows[0]["phase"] == "daily" and rows[0]["status"] == "success"


@pytest.mark.anyio
async def test_resources_and_prompt(client: Client):
    types = json.loads((await client.read_resource("siem://event-types")).contents[0].text)
    assert "Battles" in types
    cov = json.loads((await client.read_resource("siem://coverage")).contents[0].text)
    assert cov["mode"] == "synthetic"
    schema = (await client.read_resource("siem://schema")).contents[0].text
    assert "acled_events" in schema
    p = await client.get_prompt("situation_brief", {"country": "Niger", "date_start": "2025-01-01", "date_end": "2025-06-30"})
    assert "Niger" in p.messages[0].content.text
