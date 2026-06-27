from __future__ import annotations

from dataclasses import dataclass
import os

from psycopg.conninfo import make_conninfo


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _optional_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


@dataclass(frozen=True, slots=True)
class IngestSettings:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    acled_email: str | None = None
    acled_password: str | None = None
    jwt_secret: str | None = None
    acled_auth_url: str = "https://acleddata.com/oauth/token"
    acled_events_url: str = "https://acleddata.com/api/acled/read"
    request_timeout_seconds: int = 30
    page_limit: int = 5000

    @classmethod
    def from_env(
        cls,
        *,
        require_acled: bool = False,
        require_jwt: bool = False,
    ) -> "IngestSettings":
        acled_email = os.getenv("ACLED_EMAIL")
        acled_password = os.getenv("ACLED_PASSWORD")
        jwt_secret = os.getenv("JWT_SECRET")
        if require_acled and (not acled_email or not acled_password):
            raise RuntimeError("ACLED_EMAIL and ACLED_PASSWORD are required for ACLED sync commands")
        if require_jwt and not jwt_secret:
            raise RuntimeError("JWT_SECRET is required")
        return cls(
            db_host=_required_env("DB_HOST"),
            db_port=int(_required_env("DB_PORT")),
            db_name=_required_env("DB_NAME"),
            db_user=_required_env("DB_USER"),
            db_password=_required_env("DB_PASSWORD"),
            acled_email=acled_email,
            acled_password=acled_password,
            jwt_secret=jwt_secret,
            acled_auth_url=os.getenv("ACLED_AUTH_URL", "https://acleddata.com/oauth/token"),
            acled_events_url=os.getenv("ACLED_EVENTS_URL", "https://acleddata.com/api/acled/read"),
            request_timeout_seconds=_optional_int_env("REQUEST_TIMEOUT_SECONDS", 30),
            page_limit=_optional_int_env("ACLED_PAGE_LIMIT", 5000),
        )

    @property
    def conninfo(self) -> str:
        return make_conninfo(
            host=self.db_host,
            port=self.db_port,
            dbname=self.db_name,
            user=self.db_user,
            password=self.db_password,
        )
