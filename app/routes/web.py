"""HTML pages. They call the same service functions as the JSON API."""

import csv
import io
from collections.abc import Mapping
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Annotated
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app import i18n, services
from app.db import get_session
from app.models import Category, Issue, Severity, Status
from app.schemas import (
    DeleteRequest,
    IssueCreate,
    IssueFilters,
    IssueListParams,
    Period,
    ResolveRequest,
)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

templates = Jinja2Templates(directory=TEMPLATES_DIR)

# HTML pages are not part of the API, so they stay out of /docs.
router = APIRouter(include_in_schema=False)

SessionDep = Annotated[Session, Depends(get_session)]

FILTER_FIELDS = ("q", "clinic", "category", "status", "severity")


def render(request: Request, template: str, context: dict, status_code: int = 200) -> HTMLResponse:
    language = i18n.get_language(request)
    tz = request.app.state.settings.timezone
    # Where the language switch sends the user back to. After a POST (a form
    # shown again with errors) the URL cannot be reloaded, so use the page's GET.
    if request.method == "GET":
        current_url = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    else:
        current_url = "/issues/new" if context.get("active") == "new" else "/issues"
    context = {
        "lang": language,
        "t": partial(i18n.translate, language),
        "datetime_text": partial(i18n.format_datetime, tz=tz, language=language),
        "short_date": partial(i18n.format_short_date, language=language),
        "duration": partial(i18n.format_duration, language=language),
        "current_url": current_url,
        **context,
    }
    return templates.TemplateResponse(request, template, context, status_code=status_code)


@router.get("/")
def home() -> RedirectResponse:
    return RedirectResponse("/issues", status_code=303)


def is_local_path(url: str) -> bool:
    """True for a path on this site ('/issues?x=1'), false for '//other.site' or a full URL."""
    return url.startswith("/") and not url.startswith("//") and "\\" not in url


@router.post("/language")
def set_language(
    lang: Annotated[str, Form()] = "",
    next_url: Annotated[str, Form(alias="next")] = "/issues",
) -> RedirectResponse:
    """The EN/IT switch: remember the choice in a cookie and go back to the same page."""
    target = next_url if is_local_path(next_url) else "/issues"
    response = RedirectResponse(target, status_code=303)
    if lang in i18n.LANGUAGES:
        response.set_cookie(
            i18n.COOKIE_NAME, lang, max_age=365 * 24 * 3600, httponly=True, samesite="lax"
        )
    return response


def filter_query(filters: IssueFilters, **extra: object) -> str:
    """Query string with the active filters (and extra params), for links and redirects."""
    pairs = [(name, getattr(filters, name)) for name in FILTER_FIELDS]
    pairs += list(extra.items())
    return urlencode([(name, str(value)) for name, value in pairs if value is not None])


def list_notice(request: Request) -> dict | None:
    """Confirmation after a Post/Redirect/Get, e.g. ?created=42, as a translation key and id."""
    for event in ("created", "resolved", "reopened", "deleted", "restored"):
        value = request.query_params.get(event, "")
        if value.isdigit():
            return {"key": f"notice.{event}", "id": int(value)}
    return None


def parse_list_params(query: Mapping[str, str]) -> tuple[IssueListParams, bool]:
    """Filters and page from a query string. Invalid values fall back to no
    filters (and True), so a bad shared link still opens the page."""
    try:
        return IssueListParams.model_validate(dict(query)), False
    except ValidationError:
        return IssueListParams(), True


def render_issue_list(
    request: Request,
    session: Session,
    params: IssueListParams,
    filter_error: bool = False,
    note_error: dict | None = None,
    delete_error: dict | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    page = services.list_issues(session, params, page=params.page)
    clinics = services.list_clinic_names(session)
    selected_clinic = None
    if params.clinic is not None:
        key = services.clinic_key(params.clinic)
        selected_clinic = next((name for name in clinics if name.casefold() == key), None)

    context = {
        "active": "issues",
        "page": page,
        "filters": params,
        "filtered": any(getattr(params, name) is not None for name in FILTER_FIELDS),
        "clinics": clinics,
        "selected_clinic": selected_clinic,
        "categories": list(Category),
        "statuses": list(Status),
        "severities": list(Severity),
        "page_query": lambda number: filter_query(params, page=number),
        "export_query": filter_query(params),
        "return_query": filter_query(params, page=params.page if params.page > 1 else None),
        "notice": list_notice(request),
        "filter_error": filter_error,
        "note_error": note_error,
        "delete_error": delete_error,
    }
    return render(request, "issues.html", context, status_code=status_code)


@router.get("/issues")
def issue_list(request: Request, session: SessionDep) -> HTMLResponse:
    # Validated by hand (not as a FastAPI query model) so that a bad value in a
    # shared link shows the page with a message instead of a JSON error.
    params, filter_error = parse_list_params(request.query_params)
    status_code = 422 if filter_error else 200
    return render_issue_list(request, session, params, filter_error, status_code=status_code)


def form_errors(exc: ValidationError, language: str) -> dict[str, str]:
    errors: dict[str, str] = {}
    for error in exc.errors():
        errors.setdefault(str(error["loc"][0]), i18n.error_message(error, language))
    return errors


def render_form(
    request: Request,
    session: Session,
    values: dict[str, str],
    errors: dict[str, str],
    status_code: int = 200,
) -> HTMLResponse:
    context = {
        "active": "new",
        "values": values,
        "errors": errors,
        "clinics": services.list_clinic_names(session),
        "categories": list(Category),
        "severities": list(Severity),
    }
    return render(request, "issue_form.html", context, status_code=status_code)


@router.get("/issues/new")
def new_issue_form(request: Request, session: SessionDep) -> HTMLResponse:
    return render_form(request, session, values={}, errors={})


@router.post("/issues")
def create_issue_from_form(
    request: Request,
    session: SessionDep,
    call_id: Annotated[str, Form()] = "",
    clinic: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    category: Annotated[str, Form()] = "",
    severity: Annotated[str, Form()] = "",
) -> Response:
    values = {
        "call_id": call_id,
        "clinic": clinic,
        "description": description,
        "category": category,
        "severity": severity,
    }
    try:
        data = IssueCreate.model_validate(values)
    except ValidationError as exc:
        # Re-render with the errors next to their fields and the input preserved.
        errors = form_errors(exc, i18n.get_language(request))
        return render_form(request, session, values, errors, status_code=422)

    issue = services.create_issue(session, data)
    # Post/Redirect/Get: reloading the list page cannot submit the form again.
    return RedirectResponse(f"/issues?created={issue.id}", status_code=303)


def kept_list_query(return_query: str) -> list[tuple[str, str]]:
    """The list filters and page from a submitted return_query, known keys only."""
    submitted = parse_qs(return_query)
    return [(key, submitted[key][0]) for key in (*FILTER_FIELDS, "page") if key in submitted]


def back_to_list(return_query: str, **message: int) -> RedirectResponse:
    # Back to the same filtered list. The query is rebuilt from known keys only
    # and the path is fixed, so the form cannot redirect anywhere else.
    query = urlencode([*kept_list_query(return_query), *message.items()])
    return RedirectResponse(f"/issues?{query}", status_code=303)


def issue_not_found(request: Request, issue_id: int) -> HTMLResponse:
    return render(request, "not_found.html", {"issue_id": issue_id}, status_code=404)


@router.post("/issues/{issue_id}/resolve")
def resolve_issue_from_form(
    request: Request,
    issue_id: int,
    session: SessionDep,
    return_query: Annotated[str, Form()] = "",
    note: Annotated[str, Form()] = "",
) -> Response:
    try:
        data = ResolveRequest(note=note)
    except ValidationError as exc:
        # Show the same list again, with the note form open, the error and the input.
        params, _ = parse_list_params(dict(kept_list_query(return_query)))
        note_error = {
            "issue_id": issue_id,
            "message": i18n.error_message(exc.errors()[0], i18n.get_language(request)),
            "value": note,
        }
        return render_issue_list(request, session, params, note_error=note_error, status_code=422)

    issue = services.resolve_issue(session, issue_id, note=data.note)
    if issue is None:
        return issue_not_found(request, issue_id)
    return back_to_list(return_query, resolved=issue.id)


@router.post("/issues/{issue_id}/reopen")
def reopen_issue_from_form(
    request: Request,
    issue_id: int,
    session: SessionDep,
    return_query: Annotated[str, Form()] = "",
) -> Response:
    issue = services.reopen_issue(session, issue_id)
    if issue is None:
        return issue_not_found(request, issue_id)
    return back_to_list(return_query, reopened=issue.id)


@router.post("/issues/{issue_id}/delete")
def delete_issue_from_form(
    request: Request,
    issue_id: int,
    session: SessionDep,
    return_query: Annotated[str, Form()] = "",
    reason: Annotated[str, Form()] = "",
) -> Response:
    try:
        data = DeleteRequest(reason=reason)
    except ValidationError as exc:
        # Same list again, with the delete form open, the error and the input.
        params, _ = parse_list_params(dict(kept_list_query(return_query)))
        delete_error = {
            "issue_id": issue_id,
            "message": i18n.error_message(exc.errors()[0], i18n.get_language(request)),
            "value": reason,
        }
        return render_issue_list(
            request, session, params, delete_error=delete_error, status_code=422
        )

    issue = services.delete_issue(session, issue_id, reason=data.reason)
    if issue is None:
        return issue_not_found(request, issue_id)
    # The confirmation on the list carries an Undo button (restore).
    return back_to_list(return_query, deleted=issue.id)


@router.post("/issues/{issue_id}/restore")
def restore_issue_from_form(
    request: Request,
    issue_id: int,
    session: SessionDep,
    return_query: Annotated[str, Form()] = "",
) -> Response:
    issue = services.restore_issue(session, issue_id)
    if issue is None:
        return issue_not_found(request, issue_id)
    return back_to_list(return_query, restored=issue.id)


# The CSV is data for spreadsheets, not interface text, so it is not translated.
CSV_COLUMNS = (
    "id",
    "created_at_utc",
    "call_id",
    "clinic",
    "category",
    "severity",
    "status",
    "resolved_at_utc",
    "resolution_note",
    "description",
)


def csv_cell(value: object) -> str:
    text = "" if value is None else str(value)
    # Spreadsheets run a cell that starts with one of these characters as a
    # formula (CSV injection), so it is prefixed with a quote.
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def utc_text(value: datetime | None) -> str | None:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else None


def csv_row(issue: Issue) -> list[str]:
    values = (
        issue.id,
        utc_text(issue.created_at),
        issue.call_id,
        issue.clinic_name,
        issue.category,
        issue.severity,
        issue.status,
        utc_text(issue.resolved_at),
        issue.resolution_note,
        issue.description,
    )
    return [csv_cell(value) for value in values]


@router.get("/issues.csv")
def export_issues_csv(request: Request, session: SessionDep) -> Response:
    """The currently filtered list as a CSV file, all pages."""
    params, filter_error = parse_list_params(request.query_params)
    if filter_error:
        message = i18n.translate(i18n.get_language(request), "notice.filters_invalid")
        return PlainTextResponse(message, status_code=422)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    writer.writerows(csv_row(issue) for issue in services.list_all_issues(session, params))

    filename = f"issues-{services.utc_now():%Y%m%d}.csv"
    return Response(
        # The byte order mark tells Excel the file is UTF-8 (accents display correctly).
        content="﻿" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/dashboard")
def dashboard(request: Request, session: SessionDep) -> HTMLResponse:
    # Validated by hand, like the list filters: a bad value in a shared link
    # shows the all-time dashboard with a message instead of a JSON error.
    try:
        period = Period(request.query_params.get("period") or Period.ALL)
        period_error = False
    except ValueError:
        period, period_error = Period.ALL, True
    now = services.utc_now()
    tz = request.app.state.settings.timezone
    stats = services.get_stats(session, now=now, tz=tz, period=period)
    context = {
        "active": "dashboard",
        "stats": stats,
        "periods": list(Period),
        "period_error": period_error,
        # Used for "open for 3 d" in the needs-attention list.
        "now": now,
        # Bars are scaled to the biggest bar in each chart (1 avoids dividing by zero).
        "category_max": max((row.count for row in stats.by_category), default=0) or 1,
        "clinic_max": max((row.count for row in stats.by_clinic), default=0) or 1,
        "severity_max": max((row.count for row in stats.open_by_severity), default=0) or 1,
        "age_max": max((row.count for row in stats.open_by_age), default=0) or 1,
        "daily_max": max((row.count for row in stats.created_per_day), default=0) or 1,
    }
    return render(request, "dashboard.html", context, status_code=422 if period_error else 200)
