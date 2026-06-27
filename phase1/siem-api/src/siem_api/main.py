from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from . import auth, events, metadata
from .config import ApiSettings
from .db import DatabaseProtocol, PostgresDatabase


STATIC_DIR = Path(__file__).resolve().parents[2] / "static"
INDEX_FILE = STATIC_DIR / "index.html"


def _render_index_html(settings: ApiSettings) -> str:
    template = INDEX_FILE.read_text(encoding="utf-8")
    return (
        template.replace("__MAPBOX_TOKEN__", settings.mapbox_token)
        .replace("__MAPBOX_STYLE__", settings.mapbox_style)
    )


def create_app(
    *,
    settings: ApiSettings | None = None,
    database: DatabaseProtocol | None = None,
) -> FastAPI:
    settings = settings or ApiSettings.from_env()
    managed_database = database is None
    database = database or PostgresDatabase(settings)
    index_html = _render_index_html(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if managed_database:
            assert isinstance(database, PostgresDatabase)
            await database.start()
        yield
        if managed_database:
            assert isinstance(database, PostgresDatabase)
            await database.stop()

    app = FastAPI(title="Sahel Information Environment Monitor", lifespan=lifespan)
    app.state.settings = settings
    app.state.database = database

    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(events.router, prefix="/api/v1", tags=["events"])
    app.include_router(metadata.router, prefix="/api/v1", tags=["metadata"])

    @app.get("/api/v1/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", include_in_schema=False, response_class=HTMLResponse)
    async def root() -> HTMLResponse:
        return HTMLResponse(index_html)

    @app.get("/{full_path:path}", include_in_schema=False, response_class=HTMLResponse)
    async def frontend_fallback(full_path: str, request: Request) -> HTMLResponse:
        if full_path.startswith("api/"):
            return HTMLResponse("Not Found", status_code=404)
        if request.method != "GET":
            return HTMLResponse("Method Not Allowed", status_code=405)
        return HTMLResponse(index_html)

    return app


def app_factory() -> FastAPI:
    """Uvicorn factory entry point. Requires env vars to be set."""
    return create_app(settings=ApiSettings.from_env())
