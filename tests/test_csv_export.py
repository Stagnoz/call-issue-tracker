"""Extra 4: CSV export of the currently filtered list."""

import csv
import io
from datetime import timedelta

from app import services
from tests.conftest import FIXED_NOW, make_issue


def read_csv(response) -> list[dict[str, str]]:
    text = response.content.decode("utf-8-sig")  # strips the byte order mark
    return list(csv.DictReader(io.StringIO(text)))


def test_export_headers_and_file_name(client, sample_issues):
    response = client.get("/issues.csv")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"].startswith('attachment; filename="issues-')
    assert response.content.startswith(b"\xef\xbb\xbf")  # UTF-8 byte order mark for Excel


def test_export_contains_all_fields_newest_first(client, session):
    issue = make_issue(session, call_id="call-csv", clinic="Città Salute - Milano")
    services.resolve_issue(session, issue.id, now=FIXED_NOW + timedelta(hours=5), note="Fixed.")

    rows = read_csv(client.get("/issues.csv"))

    assert rows == [
        {
            "id": str(issue.id),
            "created_at_utc": "2026-09-01 12:00:00",
            "call_id": "call-csv",
            "clinic": "Città Salute - Milano",
            "category": "booking",
            "severity": "high",
            "status": "resolved",
            "resolved_at_utc": "2026-09-01 17:00:00",
            "resolution_note": "Fixed.",
            "description": "Assistant booked a visit on a Sunday; the clinic is closed.",
        }
    ]


def test_export_follows_filters_and_search(client, sample_issues):
    rows = read_csv(client.get("/issues.csv?clinic=Clinic Alpha&status=open"))

    assert [row["call_id"] for row in rows] == ["call-0002", "call-0000"]
    assert read_csv(client.get("/issues.csv?q=call-0007"))[0]["call_id"] == "call-0007"


def test_export_is_not_paginated(client, session):
    for index in range(30):
        make_issue(session, now=FIXED_NOW + timedelta(minutes=index), call_id=f"call-{index}")

    rows = read_csv(client.get("/issues.csv?page=2"))

    assert len(rows) == 30
    assert rows[0]["call_id"] == "call-29"


def test_formula_like_cells_are_neutralised(client, session):
    make_issue(session, call_id="-call-1", description="=HYPERLINK(1) typed by a reviewer")

    row = read_csv(client.get("/issues.csv"))[0]

    assert row["call_id"] == "'-call-1"
    assert row["description"] == "'=HYPERLINK(1) typed by a reviewer"


def test_export_with_invalid_filter_returns_422(client):
    response = client.get("/issues.csv?status=closed")

    assert response.status_code == 422


def test_export_link_carries_the_current_filters(client, sample_issues):
    text = client.get("/issues?q=call&status=open&page=1").text

    assert 'href="/issues.csv?q=call&amp;status=open"' in text
    assert 'href="/issues.csv"' in client.get("/issues").text
