from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Iterable

import click

from .acled_api import AcledClient
from .config import IngestSettings
from .db import Database, chunked
from .transform import normalize_event


def _iterate_date_sync(
    client: AcledClient,
    *,
    token: str,
    date_from: date,
    date_to: date,
    page_limit: int,
) -> Iterable[dict]:
    page = 1
    while True:
        response = client.fetch_events_by_date(
            token,
            date_from=date_from,
            date_to=date_to,
            page=page,
            limit=page_limit,
        )
        if not response.events:
            return
        for event in response.events:
            yield event
        if not response.has_more:
            return
        page += 1


def _iterate_timestamp_sync(
    client: AcledClient,
    *,
    token: str,
    since_timestamp: int,
    page_limit: int,
) -> Iterable[dict]:
    page = 1
    while True:
        response = client.fetch_events_by_timestamp(
            token,
            since_timestamp=since_timestamp,
            page=page,
            limit=page_limit,
        )
        if not response.events:
            return
        for event in response.events:
            yield event
        if not response.has_more:
            return
        page += 1


def _persist_events(database: Database, raw_events: Iterable[dict]) -> tuple[int, int | None]:
    normalized = [normalize_event(event) for event in raw_events]
    if not normalized:
        return 0, None
    upserted = 0
    for batch in chunked(normalized, 500):
        upserted += database.upsert_events(list(batch))
    last_timestamp = max((event[30] for event in normalized if event[30] is not None), default=None)
    return upserted, last_timestamp


@click.group()
def main() -> None:
    """Command line entrypoint for SIEM ingestion tasks."""


@main.command("bulk-load")
@click.option("--date-from", "date_from_raw", required=True, type=click.DateTime(formats=["%Y-%m-%d"]))
@click.option("--date-to", "date_to_raw", type=click.DateTime(formats=["%Y-%m-%d"]))
def bulk_load(date_from_raw: datetime, date_to_raw: datetime | None) -> None:
    settings = IngestSettings.from_env(require_acled=True)
    database = Database(settings)
    client = AcledClient(settings)
    date_from = date_from_raw.date()
    date_to = date_to_raw.date() if date_to_raw else date.today()
    log_id = database.create_ingestion_log(
        phase="bulk-load",
        status="running",
        date_from=date_from,
        date_to=date_to,
    )
    try:
        token = client.fetch_access_token()
        upserted, last_timestamp = _persist_events(
            database,
            _iterate_date_sync(
                client,
                token=token,
                date_from=date_from,
                date_to=date_to,
                page_limit=settings.page_limit,
            ),
        )
        database.complete_ingestion_log(
            log_id,
            status="success",
            events_upserted=upserted,
            last_timestamp=last_timestamp,
        )
        click.echo(f"Bulk load complete: {upserted} events upserted")
    except Exception as error:
        database.complete_ingestion_log(
            log_id,
            status="failed",
            events_upserted=0,
            error_message=str(error),
        )
        raise


@main.command("daily-update")
def daily_update() -> None:
    settings = IngestSettings.from_env(require_acled=True)
    database = Database(settings)
    client = AcledClient(settings)
    since_timestamp = database.get_last_successful_timestamp() or 0
    log_id = database.create_ingestion_log(
        phase="daily-update",
        status="running",
        started_at=datetime.now(timezone.utc),
        last_timestamp=since_timestamp,
    )
    try:
        token = client.fetch_access_token()
        upserted, last_timestamp = _persist_events(
            database,
            _iterate_timestamp_sync(
                client,
                token=token,
                since_timestamp=since_timestamp,
                page_limit=settings.page_limit,
            ),
        )
        database.complete_ingestion_log(
            log_id,
            status="success",
            events_upserted=upserted,
            last_timestamp=last_timestamp,
        )
        click.echo(f"Daily update complete: {upserted} events upserted")
    except Exception as error:
        database.complete_ingestion_log(
            log_id,
            status="failed",
            events_upserted=0,
            error_message=str(error),
            last_timestamp=since_timestamp,
        )
        raise


@main.command("create-user")
@click.option("--username", required=True)
@click.option("--password", required=True, hide_input=True, confirmation_prompt=True)
@click.option("--display-name")
def create_user(username: str, password: str, display_name: str | None) -> None:
    settings = IngestSettings.from_env()
    database = Database(settings)
    database.create_user(username=username, password=password, display_name=display_name)
    click.echo(f"User {username} created or updated")


if __name__ == "__main__":
    main()
