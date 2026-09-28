"""Dashboard backlog (age, needs attention) and flow numbers for a period."""

from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest

from app import services
from app.schemas import Period
from tests.conftest import FIXED_NOW, make_issue

ROME = ZoneInfo("Europe/Rome")
# FIXED_NOW is 1 Sep 2026, 12:00 UTC = 14:00 in Rome. The 7-day period is
# 26 Aug to 1 Sep in Rome, so it starts at 25 Aug 22:00 UTC; the previous
# period starts at 18 Aug 22:00 UTC.


def stats_for(session, period):
    return services.get_stats(session, now=FIXED_NOW, tz=ROME, period=period)


def test_open_issues_by_age(session):
    for age in (
        timedelta(hours=2),
        timedelta(days=1),  # exactly one day is no longer "under 1 day"
        timedelta(days=3),
        timedelta(days=10),
        timedelta(days=40),
    ):
        make_issue(session, now=FIXED_NOW - age)
    resolved = make_issue(session, now=FIXED_NOW - timedelta(days=40))
    services.resolve_issue(session, resolved.id, now=FIXED_NOW)

    ages = stats_for(session, Period.ALL).open_by_age

    assert [(row.bucket, row.count) for row in ages] == [
        ("under_1_day", 1),
        ("1_to_7_days", 2),
        ("7_to_30_days", 1),
        ("over_30_days", 1),
    ]


def test_needs_attention_lists_critical_then_high_oldest_first(session):
    new_critical = make_issue(session, now=FIXED_NOW - timedelta(days=1), severity="critical")
    old_critical = make_issue(session, now=FIXED_NOW - timedelta(days=5), severity="critical")
    highs = [
        make_issue(session, now=FIXED_NOW - timedelta(days=10 + days), severity="high")
        for days in range(4)
    ]
    make_issue(session, now=FIXED_NOW - timedelta(days=30), severity="medium")
    resolved = make_issue(session, now=FIXED_NOW - timedelta(days=30), severity="critical")
    services.resolve_issue(session, resolved.id, now=FIXED_NOW)
    deleted = make_issue(session, now=FIXED_NOW - timedelta(days=30), severity="critical")
    services.delete_issue(session, deleted.id, reason="Duplicate of another issue")

    attention = stats_for(session, Period.ALL).needs_attention

    # Five at most: both criticals, then the three oldest highs.
    assert [issue.id for issue in attention] == [
        old_critical.id,
        new_critical.id,
        highs[3].id,
        highs[2].id,
        highs[1].id,
    ]


def test_period_counts_created_and_resolved(session):
    # Created in the current period; one of them is also resolved in it.
    make_issue(session, now=FIXED_NOW - timedelta(days=1))
    both = make_issue(session, now=FIXED_NOW - timedelta(days=3))
    services.resolve_issue(session, both.id, now=FIXED_NOW - timedelta(days=1))
    # Created in the previous period, resolved in the current one.
    late = make_issue(session, now=FIXED_NOW - timedelta(days=10))
    services.resolve_issue(session, late.id, now=FIXED_NOW - timedelta(days=2))
    # Created in the previous period, still open.
    make_issue(session, now=FIXED_NOW - timedelta(days=10))
    # Created before both periods, resolved in the previous one.
    old = make_issue(session, now=FIXED_NOW - timedelta(days=20))
    services.resolve_issue(session, old.id, now=FIXED_NOW - timedelta(days=9))

    week = stats_for(session, Period.DAYS_7)

    assert (week.total, week.resolved) == (2, 2)
    assert (week.previous_total, week.previous_resolved) == (2, 1)
    # The backlog ignores the period: both open issues count.
    assert week.open == 2
    assert sum(row.count for row in week.by_category) == 2
    assert week.by_clinic[0].count == 2
    assert week.by_clinic[0].open == 1
    # Resolved in the period after 2 and 8 days: median 5 days.
    assert week.median_resolution_hours == 120

    all_time = stats_for(session, Period.ALL)

    assert (all_time.total, all_time.resolved, all_time.open) == (5, 3, 2)
    assert all_time.previous_total is None
    assert all_time.previous_resolved is None


def test_period_starts_at_local_midnight(session):
    make_issue(session, now=FIXED_NOW.replace(day=25, month=8, hour=22, minute=30))  # 26 Aug 00:30
    make_issue(session, now=FIXED_NOW.replace(day=25, month=8, hour=21, minute=30))  # 25 Aug 23:30

    week = stats_for(session, Period.DAYS_7)

    assert (week.total, week.previous_total) == (1, 1)


@pytest.mark.parametrize(
    ("period", "days"), [(Period.DAYS_7, 7), (Period.DAYS_90, 90), (Period.ALL, 30)]
)
def test_chart_covers_the_period(session, period, days):
    per_day = stats_for(session, period).created_per_day

    assert len(per_day) == days
    assert per_day[-1].day == FIXED_NOW.astimezone(ROME).date()


def test_api_stats_accepts_a_period(client, sample_issues):
    response = client.get("/api/stats", params={"period": "30"})

    assert response.status_code == 200
    assert response.json()["period"] == "30"
    assert len(response.json()["created_per_day"]) == 30


def test_api_stats_rejects_an_unknown_period(client):
    assert client.get("/api/stats", params={"period": "14"}).status_code == 422
