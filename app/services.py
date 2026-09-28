"""Service layer: every database query and business rule lives here.

Both the JSON API and the HTML pages call these functions, so the two
interfaces cannot drift apart.
"""

import math
import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo

from sqlalchemy import ColumnElement, case, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import InstrumentedAttribute, Session
from sqlalchemy.sql import Select

from app.models import Category, Clinic, Issue, Severity, Status
from app.schemas import (
    AgeCount,
    CategoryCount,
    ClinicCount,
    DayCount,
    IssueCreate,
    IssueFilters,
    IssueOut,
    Period,
    SeverityCount,
    Stats,
)

PER_PAGE = 25
# Days in the per-day chart when the dashboard shows all time.
DAILY_WINDOW_DAYS = 30
NEEDS_ATTENTION_LIMIT = 5
# Age buckets for open issues, by upper bound in days; older ones go to OLDEST_AGE_BUCKET.
AGE_BUCKETS = (("under_1_day", 1), ("1_to_7_days", 7), ("7_to_30_days", 30))
OLDEST_AGE_BUCKET = "over_30_days"

# Soft-deleted issues are excluded from every list, count and lookup.
NOT_DELETED = Issue.deleted_at.is_(None)


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
    """Clinics with at least one issue that is not deleted. A clinic created by a
    mistyped issue disappears from the suggestions once that issue is deleted."""
    statement = (
        select(Clinic.name)
        .join(Issue.clinic)
        .where(NOT_DELETED)
        .group_by(Clinic.id)
        .order_by(Clinic.name_key)
    )
    return list(session.scalars(statement))


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
    statement = statement.where(NOT_DELETED)
    if filters.clinic is not None:
        key = clinic_key(filters.clinic)
        statement = statement.join(Issue.clinic).where(Clinic.name_key == key)
    if filters.category is not None:
        statement = statement.where(Issue.category == filters.category)
    if filters.status is not None:
        statement = statement.where(Issue.status == filters.status)
    if filters.severity is not None:
        statement = statement.where(Issue.severity == filters.severity)
    if filters.q is not None:
        # Case-insensitive substring match. autoescape makes % and _ literal.
        statement = statement.where(
            Issue.description.icontains(filters.q, autoescape=True)
            | Issue.call_id.icontains(filters.q, autoescape=True)
        )
    return statement


NEWEST_FIRST = (Issue.created_at.desc(), Issue.id.desc())


def list_issues(
    session: Session, filters: IssueFilters, page: int = 1, per_page: int = PER_PAGE
) -> Page:
    """Issues matching all given filters, newest first, one page at a time."""
    total = session.scalar(_apply_filters(select(func.count(Issue.id)), filters)) or 0
    statement = (
        _apply_filters(select(Issue), filters)
        .order_by(*NEWEST_FIRST)
        .limit(per_page)
        .offset((page - 1) * per_page)
    )
    items = list(session.scalars(statement))
    return Page(items=items, total=total, page=page, per_page=per_page)


def list_all_issues(session: Session, filters: IssueFilters) -> list[Issue]:
    """Every issue matching the filters, newest first, without pagination (CSV export)."""
    statement = _apply_filters(select(Issue), filters).order_by(*NEWEST_FIRST)
    return list(session.scalars(statement))


def get_issue(session: Session, issue_id: int) -> Issue | None:
    """The issue, or None if it does not exist or is deleted."""
    issue = session.get(Issue, issue_id)
    if issue is None or issue.deleted_at is not None:
        return None
    return issue


def resolve_issue(
    session: Session, issue_id: int, now: datetime | None = None, note: str | None = None
) -> Issue | None:
    """Mark an issue as resolved, with an optional note on what was fixed.
    Returns None if the issue does not exist.

    Idempotent: resolving an already resolved issue changes nothing, so
    resolved_at and the note keep the values of the first resolution.
    """
    issue = get_issue(session, issue_id)
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
    issue = get_issue(session, issue_id)
    if issue is None:
        return None
    if issue.status != Status.OPEN:
        issue.status = Status.OPEN
        issue.resolved_at = None
        issue.resolution_note = None
        session.commit()
    return issue


def delete_issue(
    session: Session, issue_id: int, reason: str, now: datetime | None = None
) -> Issue | None:
    """Soft delete: hide the issue everywhere and record why. Returns None if the
    issue does not exist.

    Idempotent: deleting an already deleted issue changes nothing, so
    deleted_at and the reason keep the values of the first deletion.
    """
    issue = session.get(Issue, issue_id)
    if issue is None:
        return None
    if issue.deleted_at is None:
        issue.deleted_at = now or utc_now()
        issue.deletion_reason = reason
        session.commit()
    return issue


def restore_issue(session: Session, issue_id: int) -> Issue | None:
    """Undo a delete: the issue comes back unchanged, with its status and dates.
    Returns None if the issue does not exist. Restoring a visible issue changes nothing.
    """
    issue = session.get(Issue, issue_id)
    if issue is None:
        return None
    if issue.deleted_at is not None:
        issue.deleted_at = None
        issue.deletion_reason = None
        session.commit()
    return issue


def database_is_reachable(session: Session) -> bool:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False
    return True


def _count(session: Session, *conditions: ColumnElement[bool]) -> int:
    """Number of issues that are not deleted and match every condition."""
    return session.scalar(select(func.count(Issue.id)).where(NOT_DELETED, *conditions)) or 0


def _local_midnight(day: date, tz: tzinfo) -> datetime:
    return datetime.combine(day, time.min, tzinfo=tz)


def _between(
    column: InstrumentedAttribute, start: datetime | None, end: datetime | None = None
) -> list[ColumnElement[bool]]:
    """Conditions for start <= column < end. A missing bound is left out."""
    conditions = []
    if start is not None:
        conditions.append(column >= start)
    if end is not None:
        conditions.append(column < end)
    return conditions


def _age_bucket(age: timedelta) -> str:
    for name, max_days in AGE_BUCKETS:
        if age < timedelta(days=max_days):
            return name
    return OLDEST_AGE_BUCKET


def _open_by_age(session: Session, now: datetime) -> list[AgeCount]:
    """Open issues by how long they have been waiting. Computed in Python: the
    open backlog is small, and SQLite has no portable date difference."""
    created = session.scalars(
        select(Issue.created_at).where(NOT_DELETED, Issue.status == Status.OPEN)
    )
    counts = Counter(_age_bucket(now - created_at) for created_at in created)
    buckets = [name for name, _ in AGE_BUCKETS] + [OLDEST_AGE_BUCKET]
    return [AgeCount(bucket=name, count=counts.get(name, 0)) for name in buckets]


def _needs_attention(session: Session) -> list[IssueOut]:
    """Open critical issues, then open high ones, oldest first within each."""
    critical_first = case((Issue.severity == Severity.CRITICAL, 0), else_=1)
    statement = (
        select(Issue)
        .where(
            NOT_DELETED,
            Issue.status == Status.OPEN,
            Issue.severity.in_((Severity.CRITICAL, Severity.HIGH)),
        )
        .order_by(critical_first, Issue.created_at, Issue.id)
        .limit(NEEDS_ATTENTION_LIMIT)
    )
    return [IssueOut.model_validate(issue) for issue in session.scalars(statement)]


def get_stats(
    session: Session,
    now: datetime | None = None,
    tz: tzinfo = UTC,
    period: Period = Period.ALL,
) -> Stats:
    """Dashboard numbers, deleted issues excluded.

    Backlog numbers (open, by severity, by age, needs attention) describe the
    open issues right now, whatever the period. Flow numbers (created, resolved,
    median, by category, by clinic, per day) cover the period: the last N
    calendar days in tz, today included, or all time. Every category and
    severity appears, with 0 if it has no issues. Category and clinic breakdowns
    are sorted by count descending, ties alphabetically.
    """
    now = now or utc_now()
    today = now.astimezone(tz).date()
    chart_days = period.days or DAILY_WINDOW_DAYS
    first_day = today - timedelta(days=chart_days - 1)
    if period.days is None:
        start = previous_start = None
    else:
        start = _local_midnight(first_day, tz)
        previous_start = _local_midnight(first_day - timedelta(days=period.days), tz)

    # Backlog
    open_count = _count(session, Issue.status == Status.OPEN)
    severity_rows = session.execute(
        select(Issue.severity, func.count(Issue.id))
        .where(NOT_DELETED, Issue.status == Status.OPEN)
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

    # Flow
    created_in_period = _between(Issue.created_at, start)
    resolved_in_period = [Issue.status == Status.RESOLVED, *_between(Issue.resolved_at, start)]
    total = _count(session, *created_in_period)
    resolved = _count(session, *resolved_in_period)
    previous_total = previous_resolved = None
    if period.days is not None:
        previous_total = _count(session, *_between(Issue.created_at, previous_start, start))
        previous_resolved = _count(
            session,
            Issue.status == Status.RESOLVED,
            *_between(Issue.resolved_at, previous_start, start),
        )

    # SQLite has no MEDIAN function, so the durations are computed here.
    resolved_rows = session.execute(
        select(Issue.created_at, Issue.resolved_at).where(NOT_DELETED, *resolved_in_period)
    )
    hours_to_resolve = [
        (resolved_at - created_at).total_seconds() / 3600
        for created_at, resolved_at in resolved_rows
    ]
    median_hours = statistics.median(hours_to_resolve) if hours_to_resolve else None

    # count(...) FILTER (WHERE ...): the open issues within each group.
    open_in_group = func.count(Issue.id).filter(Issue.status == Status.OPEN)

    category_rows = session.execute(
        select(Issue.category, func.count(Issue.id), open_in_group)
        .where(NOT_DELETED, *created_in_period)
        .group_by(Issue.category)
    )
    counts_by_category = {category: (count, open_) for category, count, open_ in category_rows}
    by_category = []
    for category in Category:
        count, open_ = counts_by_category.get(category, (0, 0))
        by_category.append(
            CategoryCount(category=category, label=category.label, count=count, open=open_)
        )
    by_category.sort(key=lambda item: (-item.count, item.label))

    clinic_rows = session.execute(
        select(Clinic.name, func.count(Issue.id), open_in_group)
        .join(Issue.clinic)
        .where(NOT_DELETED, *created_in_period)
        .group_by(Clinic.id)
    )
    by_clinic = [
        ClinicCount(clinic=name, count=count, open=open_) for name, count, open_ in clinic_rows
    ]
    by_clinic.sort(key=lambda item: (-item.count, item.clinic.casefold()))

    # Issues created per local day, today included.
    created = session.scalars(
        select(Issue.created_at).where(
            NOT_DELETED, *_between(Issue.created_at, _local_midnight(first_day, tz))
        )
    )
    per_day = Counter(created_at.astimezone(tz).date() for created_at in created)
    created_per_day = [
        DayCount(day=day, count=per_day.get(day, 0))
        for day in (first_day + timedelta(days=offset) for offset in range(chart_days))
    ]

    return Stats(
        period=period,
        open=open_count,
        open_critical_or_high=open_critical_or_high,
        open_by_severity=open_by_severity,
        open_by_age=_open_by_age(session, now),
        needs_attention=_needs_attention(session),
        total=total,
        resolved=resolved,
        previous_total=previous_total,
        previous_resolved=previous_resolved,
        median_resolution_hours=median_hours,
        by_category=by_category,
        by_clinic=by_clinic,
        created_per_day=created_per_day,
    )
