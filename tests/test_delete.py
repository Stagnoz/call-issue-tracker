"""Soft delete and restore: a deleted issue is hidden everywhere but kept, and can come back."""

from datetime import timedelta

import pytest

from app import services
from app.models import Issue
from app.seed import seed_if_empty
from tests.conftest import FIXED_NOW, make_issue

REASON = {"reason": "Duplicate of another issue."}


def delete(client, issue_id, body=REASON):
    return client.post(f"/api/issues/{issue_id}/delete", json=body)


def test_delete_hides_the_issue_but_keeps_the_row(client, session):
    issue = make_issue(session)

    response = delete(client, issue.id, {"reason": "  Created by mistake.  "})

    assert response.status_code == 204
    assert client.get(f"/api/issues/{issue.id}").status_code == 404
    assert client.get("/api/issues").json()["total"] == 0
    session.expire_all()
    stored = session.get(Issue, issue.id)
    assert stored.deleted_at is not None
    assert stored.deletion_reason == "Created by mistake."


@pytest.mark.parametrize(
    ("body", "error_type"),
    [
        ({}, "missing"),
        ({"reason": "   "}, "string_too_short"),
        ({"reason": "ok"}, "string_too_short"),
        ({"reason": "x" * 501}, "string_too_long"),
        ({"reason": "Patient asked to be called on 347 123 4567."}, "personal_data"),
        ({"reason": "Duplicate\u200b"}, "invisible_characters"),
        ({"reason": "Duplicate.", "deleted_at": "2026-01-01"}, "extra_forbidden"),
    ],
)
def test_invalid_reason_is_rejected_and_nothing_is_deleted(client, session, body, error_type):
    issue = make_issue(session)

    response = delete(client, issue.id, body)

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == error_type
    assert client.get(f"/api/issues/{issue.id}").status_code == 200


def test_delete_without_body_is_rejected(client, session):
    issue = make_issue(session)

    assert client.post(f"/api/issues/{issue.id}/delete").status_code == 422
    assert client.get(f"/api/issues/{issue.id}").status_code == 200


def test_delete_is_not_possible_with_get(client, session):
    issue = make_issue(session)

    assert client.get(f"/api/issues/{issue.id}/delete").status_code == 405
    assert client.get(f"/api/issues/{issue.id}").status_code == 200


def test_second_delete_keeps_the_first_reason_and_time(client, session):
    issue = make_issue(session)
    delete(client, issue.id, {"reason": "First reason."})
    session.expire_all()
    first_time = session.get(Issue, issue.id).deleted_at

    response = delete(client, issue.id, {"reason": "Second reason."})

    assert response.status_code == 204
    session.expire_all()
    stored = session.get(Issue, issue.id)
    assert stored.deletion_reason == "First reason."
    assert stored.deleted_at == first_time


def test_unknown_issue_returns_404(client):
    assert delete(client, 999).status_code == 404
    assert client.post("/api/issues/999/restore").status_code == 404


def test_deleted_issue_cannot_be_resolved_or_reopened(client, session):
    issue = make_issue(session)
    delete(client, issue.id)

    assert client.post(f"/api/issues/{issue.id}/resolve").status_code == 404
    assert client.post(f"/api/issues/{issue.id}/reopen").status_code == 404


def test_restore_brings_the_issue_back_unchanged(client, session):
    issue = make_issue(session)
    resolved = client.post(f"/api/issues/{issue.id}/resolve", json={"note": "Prompt fixed."})
    delete(client, issue.id)

    response = client.post(f"/api/issues/{issue.id}/restore")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "resolved"
    assert body["resolved_at"] == resolved.json()["resolved_at"]
    assert body["resolution_note"] == "Prompt fixed."
    assert client.get("/api/issues").json()["total"] == 1
    session.expire_all()
    assert session.get(Issue, issue.id).deletion_reason is None


def test_restoring_a_visible_issue_changes_nothing(client, session):
    issue = make_issue(session)

    response = client.post(f"/api/issues/{issue.id}/restore")

    assert response.status_code == 200
    assert response.json()["status"] == "open"


def test_deleted_issues_are_left_out_of_filters_and_search(client, session, sample_issues):
    delete(client, sample_issues[3].id)  # Clinic Beta, booking, critical, open

    assert client.get("/api/issues?category=booking").json()["total"] == 3
    assert client.get("/api/issues?clinic=Clinic Beta").json()["total"] == 2
    assert client.get("/api/issues?q=call-0003").json()["total"] == 0


def test_deleted_issues_are_left_out_of_the_stats(client, sample_issues):
    delete(client, sample_issues[3].id)  # Clinic Beta, booking, critical, open

    stats = client.get("/api/stats").json()

    assert stats["total"] == 7
    assert stats["open"] == 5
    assert stats["resolved"] == 2
    booking = next(row for row in stats["by_category"] if row["category"] == "booking")
    assert booking["count"] == 3
    beta = next(row for row in stats["by_clinic"] if row["clinic"] == "Clinic Beta")
    assert beta["count"] == 2
    critical = next(row for row in stats["open_by_severity"] if row["severity"] == "critical")
    assert critical["count"] == 0
    assert stats["open_critical_or_high"] == 2


def test_deleted_issue_leaves_the_daily_count_and_the_median(session):
    kept = make_issue(session, now=FIXED_NOW)
    removed = make_issue(session, now=FIXED_NOW)
    services.resolve_issue(session, kept.id, now=FIXED_NOW + timedelta(hours=2))
    services.resolve_issue(session, removed.id, now=FIXED_NOW + timedelta(hours=40))
    services.delete_issue(session, removed.id, reason="Created twice.")

    stats = services.get_stats(session, now=FIXED_NOW)

    assert stats.median_resolution_hours == 2
    assert stats.created_per_day[-1].count == 1


def test_clinic_with_only_deleted_issues_disappears(client, session, sample_issues):
    delete(client, sample_issues[6].id)  # both Clinic Gamma issues
    delete(client, sample_issues[7].id)

    clinics = [row["clinic"] for row in client.get("/api/stats").json()["by_clinic"]]

    assert "Clinic Gamma" not in clinics
    assert services.list_clinic_names(session) == ["Clinic Alpha", "Clinic Beta"]


def test_deleted_issues_are_left_out_of_the_csv(client, sample_issues):
    delete(client, sample_issues[3].id)

    csv_text = client.get("/issues.csv").text

    assert "call-0003" not in csv_text
    assert "call-0002" in csv_text


def test_seed_does_not_refill_a_database_whose_issues_are_all_deleted(session):
    issue = make_issue(session)
    services.delete_issue(session, issue.id, reason="Test issue.")

    assert seed_if_empty(session) == 0


# HTML


def test_every_issue_in_the_list_has_a_delete_form(client, sample_issues):
    text = client.get("/issues").text

    assert text.count('<details class="resolve delete-issue">') == len(sample_issues)
    assert f'action="/issues/{sample_issues[1].id}/delete"' in text  # resolved too


def test_delete_from_list_keeps_filters_and_offers_undo(client, sample_issues):
    issue = sample_issues[0]

    response = client.post(
        f"/issues/{issue.id}/delete",
        data={"reason": "Created by mistake.", "return_query": "clinic=Clinic Alpha&status=open"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/issues?clinic=Clinic+Alpha&status=open&deleted={issue.id}"
    )
    page = client.get(response.headers["location"]).text
    assert f"Issue #{issue.id} deleted." in page
    assert f'action="/issues/{issue.id}/restore"' in page
    assert issue.call_id not in page


def test_undo_restores_the_issue_and_keeps_filters(client, sample_issues):
    issue = sample_issues[0]
    client.post(f"/issues/{issue.id}/delete", data={"reason": "Created by mistake."})

    response = client.post(
        f"/issues/{issue.id}/restore",
        data={"return_query": "status=open"},
        follow_redirects=False,
    )

    assert response.headers["location"] == f"/issues?status=open&restored={issue.id}"
    page = client.get(response.headers["location"]).text
    assert f"Issue #{issue.id} restored." in page
    assert issue.call_id in page


def test_delete_without_reason_in_form_is_rejected(client, session):
    issue = make_issue(session)

    response = client.post(
        f"/issues/{issue.id}/delete", data={"reason": "", "return_query": "status=open"}
    )

    assert response.status_code == 422
    assert f"Issue #{issue.id} was not deleted." in response.text
    assert '<details class="resolve delete-issue" open>' in response.text
    assert "This field is required." in response.text
    assert '<option value="open" selected>' in response.text  # filters kept
    assert client.get(f"/api/issues/{issue.id}").status_code == 200


def test_invalid_reason_in_form_keeps_the_input(client, session):
    issue = make_issue(session)
    reason = "Patient wrote from mario@example.com"

    response = client.post(f"/issues/{issue.id}/delete", data={"reason": reason})

    assert response.status_code == 422
    assert f'value="{reason}"' in response.text
    assert "Remove personal data: this looks like an email address." in response.text


def test_submitting_the_delete_form_twice_is_harmless(client, session):
    issue = make_issue(session)
    form = {"reason": "Duplicate of another issue."}

    first = client.post(f"/issues/{issue.id}/delete", data=form, follow_redirects=False)
    second = client.post(f"/issues/{issue.id}/delete", data=form, follow_redirects=False)

    assert first.status_code == second.status_code == 303


def test_delete_redirect_cannot_leave_the_app(client, session):
    issue = make_issue(session)

    response = client.post(
        f"/issues/{issue.id}/delete",
        data={"reason": "Duplicate issue.", "return_query": "next=https://example.com"},
        follow_redirects=False,
    )

    assert response.headers["location"] == f"/issues?deleted={issue.id}"


def test_delete_or_restore_unknown_issue_from_form_returns_404(client):
    assert client.post("/issues/999/delete", data={"reason": "Duplicate."}).status_code == 404
    assert client.post("/issues/999/restore").status_code == 404


def test_mistyped_clinic_leaves_the_suggestions_once_its_issue_is_deleted(client, session):
    make_issue(session, clinic="Clinic Alpha")
    typo = make_issue(session, clinic="Clinic Alhpa")
    assert '<option value="Clinic Alhpa">' in client.get("/issues/new").text

    client.post(f"/issues/{typo.id}/delete", data={"reason": "Clinic name mistyped."})

    form = client.get("/issues/new").text
    assert '<option value="Clinic Alhpa">' not in form
    assert '<option value="Clinic Alpha">' in form


def test_delete_texts_are_translated(client, session):
    issue = make_issue(session)
    client.cookies.set("lang", "it")

    client.post(f"/issues/{issue.id}/delete", data={"reason": "Doppione."})
    page = client.get(f"/issues?deleted={issue.id}").text

    assert f"Segnalazione #{issue.id} eliminata." in page
    assert "Annulla</button>" in page
