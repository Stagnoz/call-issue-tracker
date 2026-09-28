"""Shared fixtures. Every test gets its own temporary SQLite file, never the real DB."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import services
from app.config import Settings
from app.main import create_app
from app.models import Issue
from app.schemas import IssueCreate

# Fixed reference time, so no test depends on the real clock.
FIXED_NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)

# The known fixture set used by filter and stats tests:
# (clinic, category, severity, resolved)
SAMPLE_ROWS = [
    ("Clinic Alpha", "booking", "high", False),
    ("Clinic Alpha", "booking", "low", True),
    ("Clinic Alpha", "information", "medium", False),
    ("Clinic Beta", "booking", "critical", False),
    ("Clinic Beta", "forwarding", "medium", True),
    ("Clinic Beta", "technical", "high", False),
    ("Clinic Gamma", "information", "low", False),
    ("Clinic Gamma", "booking", "medium", False),
]


def valid_payload(**overrides: object) -> dict:
    payload = {
        "call_id": "call-0001",
        "clinic": "Clinic Alpha",
        "description": "Assistant booked a visit on a Sunday; the clinic is closed.",
        "category": "booking",
        "severity": "high",
    }
    payload.update(overrides)
    return payload


def make_issue(session: Session, now: datetime = FIXED_NOW, **overrides: object) -> Issue:
    return services.create_issue(session, IssueCreate(**valid_payload(**overrides)), now=now)


@pytest.fixture
def database_url(tmp_path) -> str:
    return f"sqlite:///{(tmp_path / 'test.db').as_posix()}"


@pytest.fixture
def app(database_url: str) -> FastAPI:
    return create_app(Settings(database_url=database_url))


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    # The context manager runs the app lifespan, which creates the tables.
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def session(client: TestClient) -> Iterator[Session]:
    with client.app.state.session_factory() as db_session:
        yield db_session


@pytest.fixture
def sample_issues(session: Session) -> list[Issue]:
    """Eight issues across three clinics, created one hour apart (row 0 is the oldest)."""
    issues = []
    for index, (clinic, category, severity, resolved) in enumerate(SAMPLE_ROWS):
        created_at = FIXED_NOW + timedelta(hours=index)
        issue = make_issue(
            session,
            now=created_at,
            call_id=f"call-{index:04d}",
            clinic=clinic,
            category=category,
            severity=severity,
        )
        if resolved:
            services.resolve_issue(session, issue.id, now=created_at + timedelta(days=1))
        issues.append(issue)
    return issues
