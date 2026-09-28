import re
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import Settings
from app.db import init_db, make_engine, make_session_factory
from app.main import create_app
from app.models import Category, Issue, Severity, Status
from app.seed import SEED_ISSUES, seed_if_empty
from tests.conftest import FIXED_NOW, make_issue


def all_issues(session) -> list[Issue]:
    return list(session.scalars(select(Issue).order_by(Issue.id)))


def test_seed_content_is_varied_and_realistic(session):
    inserted = seed_if_empty(session, now=FIXED_NOW)
    issues = all_issues(session)

    assert inserted == len(issues) == 44
    assert len({issue.clinic_name for issue in issues}) == 6
    assert {issue.category for issue in issues} == set(Category)
    assert {issue.severity for issue in issues} == set(Severity)
    statuses = [issue.status for issue in issues]
    assert (statuses.count(Status.OPEN), statuses.count(Status.RESOLVED)) == (26, 18)


def test_seed_dates_are_in_the_last_60_days_and_consistent(session):
    seed_if_empty(session, now=FIXED_NOW)

    for issue in all_issues(session):
        assert FIXED_NOW - timedelta(days=60) <= issue.created_at < FIXED_NOW
        if issue.status == Status.RESOLVED:
            assert issue.created_at < issue.resolved_at <= FIXED_NOW
        else:
            assert issue.resolved_at is None


def test_seed_is_deterministic(tmp_path):
    snapshots = []
    for name in ("first.db", "second.db"):
        engine = make_engine(f"sqlite:///{(tmp_path / name).as_posix()}")
        init_db(engine)
        with make_session_factory(engine)() as session:
            seed_if_empty(session, now=FIXED_NOW)
            snapshots.append(
                [
                    (i.call_id, i.clinic_name, i.category, i.severity, i.created_at, i.resolved_at)
                    for i in all_issues(session)
                ]
            )
        engine.dispose()

    assert snapshots[0] == snapshots[1]


def test_seed_twice_does_not_duplicate(session):
    assert seed_if_empty(session, now=FIXED_NOW) == 44
    assert seed_if_empty(session, now=FIXED_NOW) == 0

    assert session.scalar(select(func.count(Issue.id))) == 44


def test_seed_does_not_touch_a_non_empty_database(session):
    make_issue(session, call_id="real-issue")

    assert seed_if_empty(session, now=FIXED_NOW) == 0
    assert [issue.call_id for issue in all_issues(session)] == ["real-issue"]


def test_seed_descriptions_contain_no_phone_numbers():
    # R9: demo data must not model storing patient contact details.
    for row in SEED_ISSUES:
        assert not re.search(r"\d{6,}", row.description), row.description


def test_auto_seed_on_startup_only_when_enabled(tmp_path):
    enabled = Settings(
        database_url=f"sqlite:///{(tmp_path / 'on.db').as_posix()}", seed_on_startup=True
    )
    disabled = Settings(database_url=f"sqlite:///{(tmp_path / 'off.db').as_posix()}")

    with TestClient(create_app(enabled)) as client:
        assert client.get("/api/stats").json()["total"] == 44
    # A restart with seeding still enabled must not seed again.
    with TestClient(create_app(enabled)) as client:
        assert client.get("/api/stats").json()["total"] == 44
    with TestClient(create_app(disabled)) as client:
        assert client.get("/api/stats").json()["total"] == 0
