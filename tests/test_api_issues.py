"""Creating, validating, listing and fetching issues through the JSON API."""

from datetime import UTC, datetime, timedelta

import pytest

from tests.conftest import FIXED_NOW, make_issue, valid_payload


def test_create_issue_stores_fields_and_sets_server_values(client):
    before = datetime.now(UTC)
    response = client.post("/api/issues", json=valid_payload(call_id="  call-42  "))
    after = datetime.now(UTC)

    assert response.status_code == 201
    body = response.json()
    assert body["call_id"] == "call-42"
    assert body["clinic"] == "Clinic Alpha"
    assert body["description"] == "Assistant booked a visit on a Sunday; the clinic is closed."
    assert body["category"] == "booking"
    assert body["severity"] == "high"
    assert body["status"] == "open"
    assert body["resolved_at"] is None
    created_at = datetime.fromisoformat(body["created_at"])
    assert before <= created_at <= after

    fetched = client.get(f"/api/issues/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == body


@pytest.mark.parametrize("field", ["status", "created_at"])
def test_create_issue_rejects_server_controlled_fields(client, field):
    value = "resolved" if field == "status" else "2020-01-01T00:00:00Z"
    response = client.post("/api/issues", json=valid_payload(**{field: value}))

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", field]
    assert client.get("/api/issues").json()["total"] == 0


@pytest.mark.parametrize(
    ("case", "payload"),
    [
        ("missing call_id", {k: v for k, v in valid_payload().items() if k != "call_id"}),
        ("whitespace-only description", valid_payload(description="     ")),
        ("too short description", valid_payload(description="bad")),
        ("too long description", valid_payload(description="x" * 2001)),
        ("invalid category", valid_payload(category="billing")),
        ("invalid severity", valid_payload(severity="urgent")),
        ("too long call_id", valid_payload(call_id="c" * 101)),
        ("whitespace-only clinic", valid_payload(clinic="   ")),
    ],
)
def test_create_issue_validation_errors(client, case, payload):
    response = client.post("/api/issues", json=payload)

    assert response.status_code == 422, case
    assert client.get("/api/issues").json()["total"] == 0


def test_clinic_names_differing_by_case_or_spacing_are_the_same_clinic(client):
    client.post("/api/issues", json=valid_payload(clinic="Centro Medico Aurora"))
    response = client.post("/api/issues", json=valid_payload(clinic="  centro   MEDICO aurora "))

    assert response.json()["clinic"] == "Centro Medico Aurora"
    by_clinic = client.get("/api/stats").json()["by_clinic"]
    assert by_clinic == [{"clinic": "Centro Medico Aurora", "count": 2}]


def test_list_returns_newest_first(client, session):
    # Created out of order on purpose; two issues share the same timestamp.
    make_issue(session, now=FIXED_NOW, call_id="middle")
    make_issue(session, now=FIXED_NOW + timedelta(days=2), call_id="newest")
    make_issue(session, now=FIXED_NOW - timedelta(days=3), call_id="oldest")
    make_issue(session, now=FIXED_NOW, call_id="middle-later-id")

    items = client.get("/api/issues").json()["items"]

    assert [item["call_id"] for item in items] == [
        "newest",
        "middle-later-id",
        "middle",
        "oldest",
    ]


def test_list_is_paginated_25_per_page(client, session):
    for index in range(30):
        make_issue(session, now=FIXED_NOW + timedelta(minutes=index), call_id=f"call-{index}")

    first = client.get("/api/issues").json()
    second = client.get("/api/issues?page=2").json()
    beyond = client.get("/api/issues?page=3").json()

    assert (first["total"], first["pages"], len(first["items"])) == (30, 2, 25)
    assert first["items"][0]["call_id"] == "call-29"
    assert len(second["items"]) == 5
    assert second["items"][-1]["call_id"] == "call-0"
    assert beyond["items"] == []
    assert client.get("/api/issues?page=0").status_code == 422


def test_get_unknown_issue_returns_404(client):
    assert client.get("/api/issues/999").status_code == 404
