"""Data written through one engine is still there after building a new one on the
same file: the app-level equivalent of restarting the container."""

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import init_db, make_engine, make_session_factory
from app.main import create_app
from app.schemas import IssueFilters
from app.services import list_issues, resolve_issue
from tests.conftest import make_issue


def test_data_survives_a_new_engine(database_url):
    first_engine = make_engine(database_url)
    init_db(first_engine)
    with make_session_factory(first_engine)() as session:
        issue = make_issue(session, call_id="persist-me")
        resolve_issue(session, issue.id)
    first_engine.dispose()

    second_engine = make_engine(database_url)
    with make_session_factory(second_engine)() as session:
        page = list_issues(session, IssueFilters())
    second_engine.dispose()

    assert page.total == 1
    assert page.items[0].call_id == "persist-me"
    assert page.items[0].status == "resolved"
    assert page.items[0].resolved_at is not None


def test_data_survives_an_app_restart(database_url):
    settings = Settings(database_url=database_url)
    payload = {
        "call_id": "call-restart",
        "clinic": "Clinic Alpha",
        "description": "Assistant hung up while reading the clinic address.",
        "category": "technical",
        "severity": "medium",
    }
    with TestClient(create_app(settings)) as client:
        issue_id = client.post("/api/issues", json=payload).json()["id"]

    with TestClient(create_app(settings)) as client:
        response = client.get(f"/api/issues/{issue_id}")

    assert response.status_code == 200
    assert response.json()["call_id"] == "call-restart"
