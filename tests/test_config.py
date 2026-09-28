from zoneinfo import ZoneInfoNotFoundError

import pytest

from app.config import Settings, load_settings


def test_defaults_without_environment(monkeypatch):
    for name in ("DATABASE_URL", "SEED_ON_STARTUP", "APP_TIMEZONE"):
        monkeypatch.delenv(name, raising=False)

    assert load_settings() == Settings(
        database_url="sqlite:///./issues.db", seed_on_startup=False, app_timezone="Europe/Rome"
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("true", True), ("TRUE", True), ("1", True), ("yes", True), ("false", False), ("0", False)],
)
def test_seed_on_startup_parsing(monkeypatch, raw, expected):
    monkeypatch.setenv("SEED_ON_STARTUP", raw)

    assert load_settings().seed_on_startup is expected


def test_invalid_seed_flag_fails_at_startup(monkeypatch):
    monkeypatch.setenv("SEED_ON_STARTUP", "maybe")

    with pytest.raises(ValueError, match="SEED_ON_STARTUP"):
        load_settings()


def test_invalid_timezone_fails_at_startup():
    with pytest.raises(ZoneInfoNotFoundError):
        Settings(app_timezone="Mars/Olympus_Mons")
