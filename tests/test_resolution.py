"""Extra 1: resolution note, reopen, and median time to resolution."""

from datetime import timedelta

import pytest

from app import services
from app.i18n import format_duration
from app.schemas import IssueFilters
from app.seed import seed_if_empty
from tests.conftest import FIXED_NOW, make_issue


def test_resolve_with_note_stores_it(client, session):
    issue = make_issue(session)

    response = client.post(
        f"/api/issues/{issue.id}/resolve", json={"note": "  Prompt updated for weekends.  "}
    )

    assert response.status_code == 200
    assert response.json()["resolution_note"] == "Prompt updated for weekends."


def test_resolve_without_body_leaves_note_empty(client, session):
    issue = make_issue(session)

    body = client.post(f"/api/issues/{issue.id}/resolve").json()

    assert body["status"] == "resolved"
    assert body["resolution_note"] is None


def test_second_resolve_keeps_the_first_note(client, session):
    issue = make_issue(session)
    first = client.post(f"/api/issues/{issue.id}/resolve", json={"note": "First fix."}).json()

    second = client.post(f"/api/issues/{issue.id}/resolve", json={"note": "Other fix."}).json()

    assert second["resolution_note"] == "First fix."
    assert second["resolved_at"] == first["resolved_at"]


@pytest.mark.parametrize(
    ("note", "error_type"),
    [
        ("x" * 501, "string_too_long"),
        ("Called the patient back on 347 123 4567.", "personal_data"),
        ("Fixed​", "invisible_characters"),
    ],
)
def test_invalid_note_is_rejected(client, session, note, error_type):
    issue = make_issue(session)

    response = client.post(f"/api/issues/{issue.id}/resolve", json={"note": note})

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == error_type
    assert client.get(f"/api/issues/{issue.id}").json()["status"] == "open"


def test_whitespace_note_counts_as_no_note(client, session):
    issue = make_issue(session)

    body = client.post(f"/api/issues/{issue.id}/resolve", json={"note": "   "}).json()

    assert body["resolution_note"] is None


def test_reopen_clears_resolution(client, session):
    issue = make_issue(session)
    client.post(f"/api/issues/{issue.id}/resolve", json={"note": "Slot sync fixed."})

    response = client.post(f"/api/issues/{issue.id}/reopen")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "open"
    assert body["resolved_at"] is None
    assert body["resolution_note"] is None


def test_reopen_open_issue_is_idempotent(client, session):
    issue = make_issue(session)

    response = client.post(f"/api/issues/{issue.id}/reopen")

    assert response.status_code == 200
    assert response.json()["status"] == "open"


def test_reopen_unknown_issue_returns_404(client):
    assert client.post("/api/issues/999/reopen").status_code == 404


def test_reopen_is_not_reachable_with_get(client, session):
    issue = make_issue(session)
    client.post(f"/api/issues/{issue.id}/resolve")

    assert client.get(f"/api/issues/{issue.id}/reopen").status_code == 405
    assert client.get(f"/api/issues/{issue.id}").json()["status"] == "resolved"


def resolve_after(session, hours: float) -> None:
    issue = make_issue(session, now=FIXED_NOW)
    services.resolve_issue(session, issue.id, now=FIXED_NOW + timedelta(hours=hours))


def test_median_time_to_resolution_odd_count(client, session):
    for hours in (2, 10, 4):
        resolve_after(session, hours)
    make_issue(session)  # open issues do not count

    assert client.get("/api/stats").json()["median_resolution_hours"] == 4


def test_median_time_to_resolution_even_count(client, session):
    for hours in (2, 4):
        resolve_after(session, hours)

    assert client.get("/api/stats").json()["median_resolution_hours"] == 3


def test_median_is_none_without_resolved_issues(client, session):
    make_issue(session)

    assert client.get("/api/stats").json()["median_resolution_hours"] is None


def test_reopened_issue_leaves_the_median(client, session):
    resolve_after(session, 2)
    resolve_after(session, 30)
    client.post("/api/issues/2/reopen")

    assert client.get("/api/stats").json()["median_resolution_hours"] == 2


@pytest.mark.parametrize(
    ("hours", "text"),
    [(0.75, "45 min"), (1, "1 h"), (20.4, "20 h"), (48, "2 d"), (52, "2 d 4 h")],
)
def test_duration_format(hours, text):
    assert format_duration(hours, "en") == text


def test_every_resolved_seed_issue_has_a_note(session):
    seed_if_empty(session, now=FIXED_NOW)

    stats = services.get_stats(session)
    resolved = services.list_issues(session, IssueFilters(status="resolved"), per_page=100)
    assert stats.median_resolution_hours is not None
    assert resolved.total == 18
    assert all(issue.resolution_note for issue in resolved.items)


# HTML


def test_resolve_form_with_note_shows_it_in_the_list(client, session):
    issue = make_issue(session)

    response = client.post(
        f"/issues/{issue.id}/resolve",
        data={"note": "Weekend rule added to the prompt.", "return_query": ""},
        follow_redirects=False,
    )
    page = client.get(response.headers["location"]).text

    assert response.status_code == 303
    assert "Weekend rule added to the prompt." in page
    assert "Reopen</button>" in page


def test_invalid_note_in_form_keeps_the_input_and_the_issue_open(client, session):
    issue = make_issue(session)
    note = "Called back on 347 123 4567."

    response = client.post(
        f"/issues/{issue.id}/resolve", data={"note": note, "return_query": "status=open"}
    )

    assert response.status_code == 422
    assert f"Issue #{issue.id} was not resolved." in response.text
    assert '<details class="resolve" open>' in response.text
    assert f'value="{note}"' in response.text
    assert "Remove personal data: this looks like a phone number." in response.text
    assert '<option value="open" selected>' in response.text  # filters kept
    assert client.get(f"/api/issues/{issue.id}").json()["status"] == "open"


def test_reopen_from_list_keeps_filters(client, session):
    issue = make_issue(session)
    services.resolve_issue(session, issue.id)

    response = client.post(
        f"/issues/{issue.id}/reopen",
        data={"return_query": "status=resolved"},
        follow_redirects=False,
    )

    assert response.headers["location"] == f"/issues?status=resolved&reopened={issue.id}"
    assert f"Issue #{issue.id} reopened." in client.get(response.headers["location"]).text
    assert client.get(f"/api/issues/{issue.id}").json()["status"] == "open"


def test_reopen_unknown_issue_from_form_returns_404(client):
    assert client.post("/issues/999/reopen").status_code == 404


def test_dashboard_shows_median(client, session):
    for hours in (2, 10, 4):
        resolve_after(session, hours)

    text = client.get("/dashboard").text

    assert "Median time to resolution" in text
    assert "4 h" in text
