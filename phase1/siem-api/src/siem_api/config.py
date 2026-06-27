from __future__ import annotations

from dataclasses import dataclass
import os

from psycopg.conninfo import make_conninfo


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True, slots=True)
class ApiSettings:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    jwt_secret: str
    jwt_ttl_days: int = 7
    mapbox_token: str = ""
    mapbox_style: str = "mapbox://styles/mapbox/dark-v11"
    host: str = "0.0.0.0"
    port: int = 80

    @classmethod
    def from_env(cls) -> "ApiSettings":
        return cls(
            db_host=_required_env("DB_HOST"),
            db_port=int(_required_env("DB_PORT")),
            db_name=_required_env("DB_NAME"),
            db_user=_required_env("DB_USER"),
            db_password=_required_env("DB_PASSWORD"),
            jwt_secret=_required_env("JWT_SECRET"),
            jwt_ttl_days=int(os.getenv("JWT_TTL_DAYS", "7")),
            mapbox_token=os.getenv("MAPBOX_ACCESS_TOKEN", ""),
            mapbox_style=os.getenv("MAPBOX_STYLE", "mapbox://styles/mapbox/dark-v11"),
            host=os.getenv("API_HOST", "0.0.0.0"),
            port=int(os.getenv("API_PORT", "80")),
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

