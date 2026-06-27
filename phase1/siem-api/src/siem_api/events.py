from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from .auth import require_authenticated_user
from .db import DatabaseProtocol


def _database(request: Request) -> DatabaseProtocol:
    return request.app.state.database


def _parse_bbox(raw_bbox: str) -> tuple[float, float, float, float]:
    try:
        west, south, east, north = [float(part.strip()) for part in raw_bbox.split(",")]
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid bbox") from error
    return west, south, east, north


def _parse_event_types(raw_event_types: str | None) -> list[str] | None:
    if not raw_event_types:
        return None
    values = [item.strip() for item in raw_event_types.split(",") if item.strip()]
    return values or None


def _feature_from_record(record: dict[str, Any]) -> dict[str, Any]:
    lon, lat = record.get("longitude"), record.get("latitude")
    geometry = {"type": "Point", "coordinates": [lon, lat]} if lon is not None and lat is not None else None
    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": {
            key: value.isoformat() if isinstance(value, date) else value
            for key, value in record.items()
            if key not in {"longitude", "latitude"}
        },
    }


router = APIRouter()


@router.get("/events")
async def list_events(
    _: Annotated[dict[str, Any], Depends(require_authenticated_user)],
    database: Annotated[DatabaseProtocol, Depends(_database)],
    date_start: date = Query(...),
    date_end: date = Query(...),
    bbox: str | None = Query(default=None, description="west,south,east,north"),
    event_type: str | None = Query(default=None),
) -> dict[str, Any]:
    records = await database.fetch_events(
        bbox=_parse_bbox(bbox) if bbox else None,
        date_start=date_start,
        date_end=date_end,
        event_types=_parse_event_types(event_type),
    )
    return {
        "type": "FeatureCollection",
        "features": [_feature_from_record(record) for record in records],
    }


@router.get("/events/{event_id}")
async def get_event(
    event_id: str,
    _: Annotated[dict[str, Any], Depends(require_authenticated_user)],
    database: Annotated[DatabaseProtocol, Depends(_database)],
) -> dict[str, Any]:
    record = await database.fetch_event(event_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return _feature_from_record(record)

