from __future__ import annotations

import unittest
from datetime import date, datetime, timezone

import bcrypt
from fastapi.testclient import TestClient

from siem_api.config import ApiSettings
from siem_api.main import create_app


class FakeDatabase:
    def __init__(self) -> None:
        self.password_hash = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode("utf-8")

    async def authenticate_user(self, username: str) -> dict[str, object] | None:
        if username != "jalal":
            return None
        return {
            "id": 1,
            "username": "jalal",
            "display_name": "Test User",
            "password_hash": self.password_hash,
            "is_active": True,
        }

    async def fetch_events(
        self,
        *,
        bbox: tuple[float, float, float, float] | None,
        date_start: date,
        date_end: date,
        event_types: list[str] | None,
    ) -> list[dict[str, object]]:
        if event_types == ["Battles"]:
            return []
        return [
            {
                "event_id_cnty": "BFO12345",
                "event_type": "Battles",
                "fatalities": 12,
                "longitude": -1.6306,
                "latitude": 14.0992,
            }
        ]

    async def fetch_event(self, event_id: str) -> dict[str, object] | None:
        if event_id != "BFO12345":
            return None
        return {
            "event_id_cnty": "BFO12345",
            "event_date": date(2025, 11, 15),
            "event_type": "Battles",
            "sub_event_type": "Armed clash",
            "actor1": "Military Forces of Burkina Faso",
            "actor2": "JNIM",
            "fatalities": 12,
            "country": "Burkina Faso",
            "admin1": "Sahel",
            "location": "Djibo",
            "source": "ACLED",
            "notes": "Detailed notes",
            "longitude": -1.6306,
            "latitude": 14.0992,
        }

    async def fetch_metadata(self) -> dict[str, object]:
        return {
            "latest_date": date(2026, 4, 3),
            "earliest_date": date(2019, 1, 1),
            "total_events": 38123,
            "last_updated": datetime(2026, 4, 4, 6, 0, tzinfo=timezone.utc),
        }


class AppTests(unittest.TestCase):
    def setUp(self) -> None:
        settings = ApiSettings(
            db_host="localhost",
            db_port=5432,
            db_name="siem",
            db_user="user",
            db_password="password",
            jwt_secret="development-secret-at-least-32-bytes",
            jwt_ttl_days=7,
        )
        self.client = TestClient(create_app(settings=settings, database=FakeDatabase()))

    def test_root_serves_static_frontend(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Sahel Information Environment Monitor", response.text)

    def test_healthz_is_public(self) -> None:
        response = self.client.get("/api/v1/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_login_returns_bearer_token_for_valid_credentials(self) -> None:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"username": "jalal", "password": "secret"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.json())

    def test_events_reject_missing_authorization(self) -> None:
        response = self.client.get(
            "/api/v1/events",
            params={
                "bbox": "-5,10,5,20",
                "date_start": "2025-11-09",
                "date_end": "2025-11-15",
            },
        )

        self.assertEqual(response.status_code, 401)

    def test_events_return_geojson_for_authorized_request(self) -> None:
        token = self.client.post(
            "/api/v1/auth/login",
            json={"username": "jalal", "password": "secret"},
        ).json()["token"]

        response = self.client.get(
            "/api/v1/events",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "bbox": "-5,10,5,20",
                "date_start": "2025-11-09",
                "date_end": "2025-11-15",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["type"], "FeatureCollection")
        self.assertEqual(payload["features"][0]["geometry"]["coordinates"], [-1.6306, 14.0992])
        self.assertEqual(payload["features"][0]["properties"]["event_id_cnty"], "BFO12345")
        self.assertEqual(payload["features"][0]["properties"]["event_type"], "Battles")

    def test_metadata_returns_summary_for_authorized_request(self) -> None:
        token = self.client.post(
            "/api/v1/auth/login",
            json={"username": "jalal", "password": "secret"},
        ).json()["token"]

        response = self.client.get(
            "/api/v1/metadata",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total_events"], 38123)


if __name__ == "__main__":
    unittest.main()
