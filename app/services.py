"""Service layer: every database query and business rule lives here.

Both the JSON API and the HTML pages call these functions, so the two
interfaces cannot drift apart.
"""

import math
import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta, tzinfo

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.models import Category, Clinic, Issue, Severity, Status
from app.schemas import (
    CategoryCount,
    ClinicCount,
    DayCount,
    IssueCreate,
    IssueFilters,
    SeverityCount,
    Stats,
)

PER_PAGE = 25
DAILY_WINDOW_DAYS = 30


@dataclass
class Page:
    items: list[Issue]
    total: int
    page: int
    per_page: int

    @property
    def pages(self) -> int:
        return max(1, math.ceil(self.total / self.per_page))


def utc_now() -> datetime:
    return datetime.now(UTC)


def normalize_clinic_name(name: str) -> str:
    """Trim and collapse inner whitespace: '  Centro   X ' -> 'Centro X'."""
    return " ".join(name.split())


def clinic_key(name: str) -> str:
    """Comparison key that makes clinic names differing only by case or spacing equal."""
    return normalize_clinic_name(name).casefold()


def get_or_create_clinic(session: Session, name: str) -> Clinic:
    display_name = normalize_clinic_name(name)
    key = display_name.casefold()
    clinic = session.scalar(select(Clinic).where(Clinic.name_key == key))
    if clinic is None:
        clinic = Clinic(name=display_name, name_key=key)
        session.add(clinic)
        session.flush()
    return clinic


def list_clinic_names(session: Session) -> list[str]:
    return list(session.scalars(select(Clinic.name).order_by(Clinic.name_key)))


def create_issue(session: Session, data: IssueCreate, now: datetime | None = None) -> Issue:
    """Create an open issue. created_at always comes from the server clock."""
    issue = Issue(
        call_id=data.call_id,
        clinic=get_or_create_clinic(session, data.clinic),
        description=data.description,
        category=data.category,
        severity=data.severity,
        status=Status.OPEN,
        created_at=now or utc_now(),
    )
    session.add(issue)
    session.commit()
    return issue


def _apply_filters(statement: Select, filters: IssueFilters) -> Select:
    if filters.clinic is not None:
        key = clinic_key(filters.clinic)
        statement = statement.join(Issue.clinic).where(Clinic.name_key == key)
    if filters.category is not None:
        statement = statement.where(Issue.category == filters.category)
    if filters.status is not None:
        statement = statement.where(Issue.status == filters.status)
    if filters.severity is not None:
        statement = statement.where(Issue.severity == filters.severity)
    return statement


def list_issues(
    session: Session, filters: IssueFilters, page: int = 1, per_page: int = PER_PAGE
) -> Page:
    """Issues matching all given filters, newest first, one page at a time."""
    total = session.scalar(_apply_filters(select(func.count(Issue.id)), filters)) or 0
    statement = (
        _apply_filters(select(Issue), filters)
        .order_by(Issue.created_at.desc(), Issue.id.desc())
        .limit(per_page)
        .offset((page - 1) * per_page)
    )
    items = list(session.scalars(statement))
    return Page(items=items, total=total, page=page, per_page=per_page)


def get_issue(session: Session, issue_id: int) -> Issue | None:
    return session.get(Issue, issue_id)


def resolve_issue(
    session: Session, issue_id: int, now: datetime | None = None, note: str | None = None
) -> Issue | None:
    """Mark an issue as resolved, with an optional note on what was fixed.
    Returns None if the issue does not exist.

    Idempotent: resolving an already resolved issue changes nothing, so
    resolved_at and the note keep the values of the first resolution.
    """
    issue = session.get(Issue, issue_id)
    if issue is None:
        return None
    if issue.status != Status.RESOLVED:
        issue.status = Status.RESOLVED
        issue.resolved_at = now or utc_now()
        issue.resolution_note = note
        session.commit()
    return issue


def reopen_issue(session: Session, issue_id: int) -> Issue | None:
    """Move a resolved issue back to open, clearing resolved_at and the note.
    Returns None if the issue does not exist. Reopening an open issue changes nothing.
    """
    issue = session.get(Issue, issue_id)
    if issue is None:
        return None
    if issue.status != Status.OPEN:
        issue.status = Status.OPEN
        issue.resolved_at = None
        issue.resolution_note = None
        session.commit()
    return issue


def database_is_reachable(session: Session) -> bool:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False
    return True


def get_stats(session: Session, now: datetime | None = None, tz: tzinfo = UTC) -> Stats:
    """Dashboard numbers. Every category and severity appears, with 0 if it has
    no issues. Category and clinic breakdowns are sorted by count descending,
    ties alphabetically. Days for the daily counts are calendar days in tz."""
    total = session.scalar(select(func.count(Issue.id))) or 0
    open_count = (
        session.scalar(select(func.count(Issue.id)).where(Issue.status == Status.OPEN)) or 0
    )

    category_rows = session.execute(
        select(Issue.category, func.count(Issue.id)).group_by(Issue.category)
    )
    counts_by_category = {category: count for category, count in category_rows}
    by_category = [
        CategoryCount(
            category=category, label=category.label, count=counts_by_category.get(category, 0)
        )
        for category in Category
    ]
    by_category.sort(key=lambda item: (-item.count, item.label))

    clinic_rows = session.execute(
        select(Clinic.name, func.count(Issue.id)).join(Issue.clinic).group_by(Clinic.id)
    )
    by_clinic = [ClinicCount(clinic=name, count=count) for name, count in clinic_rows]
    by_clinic.sort(key=lambda item: (-item.count, item.clinic.casefold()))

    # SQLite has no MEDIAN function, so the durations are computed here.
    resolved_rows = session.execute(
        select(Issue.created_at, Issue.resolved_at).where(Issue.status == Status.RESOLVED)
    )
    hours_to_resolve = [
        (resolved_at - created_at).total_seconds() / 3600
        for created_at, resolved_at in resolved_rows
    ]
    median_hours = statistics.median(hours_to_resolve) if hours_to_resolve else None

    severity_rows = session.execute(
        select(Issue.severity, func.count(Issue.id))
        .where(Issue.status == Status.OPEN)
        .group_by(Issue.severity)
    )
    open_counts = {severity: count for severity, count in severity_rows}
    open_by_severity = [
        SeverityCount(severity=severity, label=severity.label, count=open_counts.get(severity, 0))
        for severity in reversed(Severity)
    ]
    open_critical_or_high = open_counts.get(Severity.CRITICAL, 0) + open_counts.get(
        Severity.HIGH, 0
    )

    # Issues created per local day over the last DAILY_WINDOW_DAYS days, today included.
    today = (now or utc_now()).astimezone(tz).date()
    first_day = today - timedelta(days=DAILY_WINDOW_DAYS - 1)
    window_start = datetime.combine(first_day, time.min, tzinfo=tz)
    created = session.scalars(select(Issue.created_at).where(Issue.created_at >= window_start))
    per_day = Counter(created_at.astimezone(tz).date() for created_at in created)
    created_per_day = [
        DayCount(day=day, count=per_day.get(day, 0))
        for day in (first_day + timedelta(days=offset) for offset in range(DAILY_WINDOW_DAYS))
    ]

    return Stats(
        total=total,
        open=open_count,
        resolved=total - open_count,
        median_resolution_hours=median_hours,
        by_category=by_category,
        by_clinic=by_clinic,
        open_by_severity=open_by_severity,
        open_critical_or_high=open_critical_or_high,
        created_per_day=created_per_day,
    )
