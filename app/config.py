"""Application settings, read from environment variables with safe defaults."""

import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off", ""}


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./issues.db"
    seed_on_startup: bool = False
    app_timezone: str = "Europe/Rome"

    def __post_init__(self) -> None:
        # Fail at startup, not on the first page render, if the timezone is wrong.
        ZoneInfo(self.app_timezone)

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.app_timezone)


def _parse_bool(name: str, value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError(f"{name} must be true or false, got {value!r}")


def load_settings() -> Settings:
    defaults = Settings()
    return Settings(
        database_url=os.getenv("DATABASE_URL", defaults.database_url),
        seed_on_startup=_parse_bool("SEED_ON_STARTUP", os.getenv("SEED_ON_STARTUP", "false")),
        app_timezone=os.getenv("APP_TIMEZONE", defaults.app_timezone),
    )
