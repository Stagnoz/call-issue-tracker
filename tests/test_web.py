"""HTML pages: smoke tests, form handling, resolve from the list and escaping."""

import re
from datetime import timedelta

from tests.conftest import FIXED_NOW, make_issue


def valid_form(**overrides: str) -> dict[str, str]:
    form = {
        "call_id": "call-form-1",
        "clinic": "Clinic Alpha",
        "description": "Assistant gave the wrong opening hours for Saturday.",
        "category": "information",
        "severity": "medium",
    }
    form.update(overrides)
    return form


def test_home_redirects_to_issue_list(client):
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/issues"


def test_issue_list_page(client, sample_issues):
    response = client.get("/issues")

    assert response.status_code == 200
    assert "8 issues, newest first" in response.text
    assert "Clinic Alpha" in response.text
    assert "Mark as resolved" in response.text
    assert 'href="/dashboard"' in response.text


def test_list_shows_times_in_display_timezone(client, session):
    make_issue(session, now=FIXED_NOW)  # 12:00 UTC is 14:00 in Rome (summer time)

    assert "1 Sep 2026, 14:00" in client.get("/issues").text


def test_list_filters_from_query_string(client, sample_issues):
    response = client.get("/issues?clinic=clinic+alpha&category=booking&status=open")

    assert response.status_code == 200
    assert "1 issue matching these filters" in response.text
    assert "call-0000" in response.text
    assert "call-0001" not in response.text
    # The filters stay selected after the reload.
    assert '<option value="Clinic Alpha" selected>' in response.text
    assert '<option value="booking" selected>' in response.text
    assert '<option value="open" selected>' in response.text
    assert 'href="/issues">Clear filters</a>' in response.text


def test_list_empty_state(client, sample_issues):
    response = client.get("/issues?category=other")

    assert "No issues match these filters." in response.text


def test_list_with_invalid_filter_shows_message(client, sample_issues):
    response = client.get("/issues?category=billing")

    assert response.status_code == 422
    assert "not valid" in response.text
    assert "8 issues" in response.text


def test_list_pagination_keeps_filters(client, session):
    for index in range(30):
        make_issue(session, now=FIXED_NOW + timedelta(minutes=index), call_id=f"call-{index}")

    first = client.get("/issues?status=open")
    second = client.get("/issues?status=open&page=2")

    assert "Page 1 of 2" in first.text
    assert 'href="/issues?status=open&amp;page=2"' in first.text
    assert len(re.findall(r"<code[^>]*>call-\d+</code>", first.text)) == 25
    assert len(re.findall(r"<code[^>]*>call-\d+</code>", second.text)) == 5


def test_new_issue_form_page(client, sample_issues):
    response = client.get("/issues/new")

    assert response.status_code == 200
    for label in ("Call ID", "Clinic", "Category", "Severity", "Description"):
        assert f">{label}</label>" in response.text
    assert "Do not include patient names, phone numbers or health details." in response.text
    assert '<datalist id="clinic-options">' in response.text
    assert '<option value="Clinic Gamma">' in response.text


def test_form_post_creates_issue_and_redirects(client):
    response = client.post("/issues", data=valid_form(), follow_redirects=False)

    assert response.status_code == 303
    issue_id = int(response.headers["location"].removeprefix("/issues?created="))
    issue = client.get(f"/api/issues/{issue_id}").json()
    assert issue["call_id"] == "call-form-1"
    assert issue["status"] == "open"

    followed = client.get(response.headers["location"])
    assert f"Issue #{issue_id} created." in followed.text


def test_form_post_ignores_a_status_field(client):
    response = client.post("/issues", data=valid_form(status="resolved"), follow_redirects=False)

    issue_id = response.headers["location"].removeprefix("/issues?created=")
    assert client.get(f"/api/issues/{issue_id}").json()["status"] == "open"


def test_invalid_form_post_rerenders_with_errors_and_input(client):
    form = valid_form(call_id="   ", description="abc", category="billing")
    response = client.post("/issues", data=form, follow_redirects=False)

    assert response.status_code == 422
    assert "The issue was not saved." in response.text
    assert '<p class="field-error" id="call_id-error">This field is required.</p>' in response.text
    assert "Must be at least 5 characters." in response.text
    assert "Choose one of the options." in response.text
    # What the user typed is still there.
    assert 'value="Clinic Alpha"' in response.text
    assert ">abc</textarea>" in response.text
    assert '<option value="medium" selected>' in response.text
    assert client.get("/api/issues").json()["total"] == 0


def test_resolve_from_list_keeps_filters(client, sample_issues):
    issue = sample_issues[0]
    response = client.post(
        f"/issues/{issue.id}/resolve",
        data={"return_query": "clinic=Clinic Alpha&status=open"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/issues?clinic=Clinic+Alpha&status=open&resolved={issue.id}"
    )
    assert client.get(f"/api/issues/{issue.id}").json()["status"] == "resolved"
    assert f"Issue #{issue.id} resolved." in client.get(response.headers["location"]).text


def test_resolve_redirect_cannot_leave_the_app(client, sample_issues):
    response = client.post(
        f"/issues/{sample_issues[0].id}/resolve",
        data={"return_query": "next=https://example.com&status=open"},
        follow_redirects=False,
    )

    assert response.headers["location"] == f"/issues?status=open&resolved={sample_issues[0].id}"


def test_resolve_unknown_issue_from_form_returns_404(client):
    response = client.post("/issues/999/resolve")

    assert response.status_code == 404
    assert "Issue #999 does not exist." in response.text


def test_dashboard_page(client, sample_issues):
    response = client.get("/dashboard")
    text = response.text

    assert response.status_code == 200
    assert re.findall(r'<span class="stat-value">(\d+)</span>', text) == ["8", "6", "2"]
    assert "Patient identification" in text  # a category with zero issues still appears
    assert "Clinic Gamma" in text
    assert "width: 100.0%" in text


def test_description_is_escaped_in_list(client):
    payload = {
        "call_id": "call-xss",
        "clinic": "Clinic Alpha",
        "description": "<script>alert('x')</script> assistant misheard the caller",
        "category": "other",
        "severity": "low",
    }
    client.post("/api/issues", json=payload)

    text = client.get("/issues").text

    assert "<script>alert" not in text
    assert "&lt;script&gt;alert(&#39;x&#39;)&lt;/script&gt;" in text


def test_stylesheet_is_served_locally(client):
    response = client.get("/static/style.css")

    assert response.status_code == 200
    assert "--brand: #1a7abf" in response.text
