"""Extra 2: open issues by severity, open critical/high counter, issues per day."""

from datetime import date, timedelta
from zoneinfo import ZoneInfo

from app import services
from tests.conftest import FIXED_NOW, make_issue

ROME = ZoneInfo("Europe/Rome")


def test_open_issues_by_severity_on_sample_set(client, sample_issues):
    stats = client.get("/api/stats").json()

    # Resolved issues are not counted; every severity appears, critical first.
    assert [(row["severity"], row["count"]) for row in stats["open_by_severity"]] == [
        ("critical", 1),
        ("high", 2),
        ("medium", 2),
        ("low", 1),
    ]
    assert stats["open_critical_or_high"] == 3


def test_severity_counts_on_empty_database(client):
    stats = client.get("/api/stats").json()

    assert [row["count"] for row in stats["open_by_severity"]] == [0, 0, 0, 0]
    assert stats["open_critical_or_high"] == 0


def test_resolving_a_critical_issue_lowers_the_counter(client, session):
    issue = make_issue(session, severity="critical")
    make_issue(session, severity="low")
    assert client.get("/api/stats").json()["open_critical_or_high"] == 1

    client.post(f"/api/issues/{issue.id}/resolve")

    assert client.get("/api/stats").json()["open_critical_or_high"] == 0


def test_created_per_day_covers_30_local_days(session):
    now = FIXED_NOW  # 1 Sep 2026, 12:00 UTC = 14:00 in Rome
    make_issue(session, now=now)
    make_issue(session, now=now - timedelta(hours=1))
    make_issue(session, now=now - timedelta(days=3))
    make_issue(session, now=now - timedelta(days=29))
    make_issue(session, now=now - timedelta(days=30))  # outside the window

    days = services.get_stats(session, now=now, tz=ROME).created_per_day

    assert len(days) == 30
    assert days[0].day == date(2026, 8, 3)
    assert days[-1].day == date(2026, 9, 1)
    counts = {row.day: row.count for row in days}
    assert counts[date(2026, 9, 1)] == 2
    assert counts[date(2026, 8, 29)] == 1
    assert counts[date(2026, 8, 3)] == 1
    assert sum(counts.values()) == 4


def test_days_follow_the_display_timezone(session):
    # 22:30 UTC on 31 Aug is 00:30 on 1 Sep in Rome.
    make_issue(session, now=FIXED_NOW.replace(day=31, month=8, hour=22, minute=30))

    rome = services.get_stats(session, now=FIXED_NOW, tz=ROME).created_per_day
    utc = services.get_stats(session, now=FIXED_NOW).created_per_day

    assert rome[-1].count == 1  # counted on 1 Sep in Rome
    assert utc[-2].count == 1  # counted on 31 Aug in UTC


def test_dashboard_shows_severity_and_daily_charts(client, sample_issues):
    text = client.get("/dashboard").text

    assert "Open issues by severity" in text
    assert "Open critical or high" in text
    assert "Issues created per day" in text
    assert text.count('<span class="daily-bar"') == 30
    assert 'href="/issues?status=open&amp;severity=critical"' in text
    assert "bar-fill-critical" in text
