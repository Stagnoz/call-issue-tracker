from datetime import UTC, datetime, timedelta

from app import services
from tests.conftest import FIXED_NOW, make_issue


def test_resolve_sets_status_and_resolved_at(client, session):
    issue = make_issue(session)

    before = datetime.now(UTC)
    response = client.post(f"/api/issues/{issue.id}/resolve")
    after = datetime.now(UTC)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "resolved"
    assert before <= datetime.fromisoformat(body["resolved_at"]) <= after
    assert client.get(f"/api/issues/{issue.id}").json()["status"] == "resolved"


def test_resolving_twice_is_idempotent(client, session):
    issue = make_issue(session)

    first = client.post(f"/api/issues/{issue.id}/resolve").json()
    second = client.post(f"/api/issues/{issue.id}/resolve")

    assert second.status_code == 200
    assert second.json()["status"] == "resolved"
    assert second.json()["resolved_at"] == first["resolved_at"]


def test_service_keeps_first_resolution_time(session):
    issue = make_issue(session)
    first_time = FIXED_NOW + timedelta(hours=1)

    services.resolve_issue(session, issue.id, now=first_time)
    resolved = services.resolve_issue(session, issue.id, now=first_time + timedelta(days=3))

    assert resolved.resolved_at == first_time


def test_resolve_unknown_issue_returns_404(client):
    response = client.post("/api/issues/999/resolve")

    assert response.status_code == 404
    assert response.json() == {"detail": "Issue not found"}


def test_resolve_is_not_reachable_with_get(client, session):
    issue = make_issue(session)

    assert client.get(f"/api/issues/{issue.id}/resolve").status_code == 405
    assert client.get(f"/api/issues/{issue.id}").json()["status"] == "open"
