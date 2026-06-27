from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import time
from typing import Any

import requests

from .config import IngestSettings


COUNTRIES = ["Mali", "Burkina Faso", "Niger"]


@dataclass(frozen=True, slots=True)
class PagedResponse:
    events: list[dict[str, Any]]
    has_more: bool


class AcledClient:
    def __init__(self, settings: IngestSettings, session: requests.Session | None = None) -> None:
        self._settings = settings
        self._session = session or requests.Session()

    def fetch_access_token(self) -> str:
        response = self._request_with_retries(
            "post",
            self._settings.acled_auth_url,
            data={
                "grant_type": "password",
                "username": self._settings.acled_email,
                "password": self._settings.acled_password,
                "client_id": "acled",
            },
        )
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise RuntimeError(f"ACLED auth response did not include access_token: {payload}")
        return str(token)

    def fetch_events_by_date(
        self,
        token: str,
        *,
        date_from: date,
        date_to: date,
        page: int,
        limit: int | None = None,
    ) -> PagedResponse:
        limit = limit or self._settings.page_limit
        response = self._request_with_retries(
            "get",
            self._settings.acled_events_url,
            headers={"Authorization": f"Bearer {token}"},
            params={
                "country": "|".join(COUNTRIES),
                "population": "full",
                "_format": "json",
                "event_date": f"{date_from.isoformat()}|{date_to.isoformat()}",
                "event_date_where": "BETWEEN",
                "page": page,
                "limit": limit,
            },
        )
        return self._parse_paged_response(response, limit=limit)

    def fetch_events_by_timestamp(
        self,
        token: str,
        *,
        since_timestamp: int,
        page: int,
        limit: int | None = None,
    ) -> PagedResponse:
        limit = limit or self._settings.page_limit
        response = self._request_with_retries(
            "get",
            self._settings.acled_events_url,
            headers={"Authorization": f"Bearer {token}"},
            params={
                "country": "|".join(COUNTRIES),
                "population": "full",
                "_format": "json",
                "timestamp": since_timestamp,
                "timestamp_where": ">",
                "page": page,
                "limit": limit,
            },
        )
        return self._parse_paged_response(response, limit=limit)

    def _parse_paged_response(self, response: requests.Response, *, limit: int) -> PagedResponse:
        payload = response.json()
        events = payload.get("data") or []
        if not isinstance(events, list):
            raise RuntimeError(f"Unexpected ACLED payload shape: {payload}")
        has_more = len(events) >= limit
        return PagedResponse(events=events, has_more=has_more)

    def _request_with_retries(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", self._settings.request_timeout_seconds)
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                response = self._session.request(method, url, **kwargs)
                response.raise_for_status()
                return response
            except requests.RequestException as error:
                last_error = error
                if attempt == 3:
                    break
                time.sleep(2 ** (attempt - 1))
        assert last_error is not None
        raise RuntimeError(f"ACLED request failed after retries: {last_error}") from last_error
