from __future__ import annotations

import unittest
from datetime import date

from psycopg.errors import IndeterminateDatatype

from siem_api.config import ApiSettings
from siem_api.db import PostgresDatabase


class FakeCursor:
    def __init__(self) -> None:
        self.rows = [
            {
                "event_id_cnty": "EVT00001",
                "event_date": date(2025, 11, 15),
                "event_type": "Battles",
                "sub_event_type": "Armed clash",
                "actor1": "Country X Armed Forces",
                "actor2": "Group Y",
                "fatalities": 12,
                "country": "Country X",
                "admin1": "Province A",
                "location": "Townsville",
                "longitude": -2.5000,
                "latitude": 10.5000,
            }
        ]

    async def __aenter__(self) -> "FakeCursor":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, query: str, params: tuple[object, ...]) -> None:
        if params[6] is None and "::text[]" not in query:
            raise IndeterminateDatatype("could not determine data type of parameter $7")

    async def fetchall(self) -> list[dict[str, object]]:
        return self.rows


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    async def __aenter__(self) -> "FakeConnection":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return self._cursor


class FakePool:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def connection(self) -> FakeConnection:
        return FakeConnection(self._cursor)


class PostgresDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_events_allows_missing_event_type_filter(self) -> None:
        settings = ApiSettings(
            db_host="localhost",
            db_port=5432,
            db_name="siem",
            db_user="user",
            db_password="password",
            jwt_secret="development-secret-at-least-32-bytes",
        )
        database = PostgresDatabase(settings)
        database._pool = FakePool(FakeCursor())  # type: ignore[assignment]

        records = await database.fetch_events(
            bbox=(-5.0, 10.0, 5.0, 20.0),
            date_start=date(2025, 11, 9),
            date_end=date(2025, 11, 15),
            event_types=None,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["event_id_cnty"], "EVT00001")


if __name__ == "__main__":
    unittest.main()
