from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from .auth import require_authenticated_user
from .db import DatabaseProtocol


def _database(request: Request) -> DatabaseProtocol:
    return request.app.state.database


router = APIRouter()


@router.get("/metadata")
async def get_metadata(
    _: Annotated[dict[str, Any], Depends(require_authenticated_user)],
    database: Annotated[DatabaseProtocol, Depends(_database)],
) -> dict[str, Any]:
    return await database.fetch_metadata()

