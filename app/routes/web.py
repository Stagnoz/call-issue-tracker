"""HTML pages. They call the same service functions as the JSON API."""

from datetime import datetime
from pathlib import Path
from typing import Annotated
from urllib.parse import parse_qs, urlencode
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app import services
from app.db import get_session
from app.models import Category, Severity, Status
from app.schemas import IssueCreate, IssueFilters, IssueListParams

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

templates = Jinja2Templates(directory=TEMPLATES_DIR)


def local_time(value: datetime, tz: ZoneInfo) -> str:
    """Format a UTC datetime in the display timezone, e.g. '28 Sep 2026, 14:05'."""
    local = value.astimezone(tz)
    return f"{local.day} {local:%b %Y, %H:%M}"


templates.env.filters["local_time"] = local_time

# HTML pages are not part of the API, so they stay out of /docs.
router = APIRouter(include_in_schema=False)

SessionDep = Annotated[Session, Depends(get_session)]

FILTER_FIELDS = ("clinic", "category", "status", "severity")


def render(request: Request, template: str, context: dict, status_code: int = 200) -> HTMLResponse:
    context = {"tz": request.app.state.settings.timezone, **context}
    return templates.TemplateResponse(request, template, context, status_code=status_code)


@router.get("/")
def home() -> RedirectResponse:
    return RedirectResponse("/issues", status_code=303)


def filter_query(filters: IssueFilters, **extra: object) -> str:
    """Query string with the active filters (and extra params), for links and redirects."""
    pairs = [(name, getattr(filters, name)) for name in FILTER_FIELDS]
    pairs += list(extra.items())
    return urlencode([(name, str(value)) for name, value in pairs if value is not None])


def list_notice(request: Request) -> str | None:
    """Confirmation message after a Post/Redirect/Get, e.g. ?created=42."""
    for key, message in (("created", "Issue #{} created."), ("resolved", "Issue #{} resolved.")):
        value = request.query_params.get(key, "")
        if value.isdigit():
            return message.format(value)
    return None


@router.get("/issues")
def issue_list(request: Request, session: SessionDep) -> HTMLResponse:
    # Validated by hand (not as a FastAPI query model) so that a bad value in a
    # shared link shows the page with a message instead of a JSON error.
    filter_error = None
    try:
        params = IssueListParams.model_validate(dict(request.query_params))
    except ValidationError:
        params = IssueListParams()
        filter_error = "Some filter values in this link are not valid, so no filters are applied."

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
        "return_query": filter_query(params, page=params.page if params.page > 1 else None),
        "notice": list_notice(request),
        "filter_error": filter_error,
    }
    return render(request, "issues.html", context, status_code=422 if filter_error else 200)


def error_message(error: dict) -> str:
    """Short, human message for one Pydantic validation error."""
    kind = error["type"]
    limits = error.get("ctx", {})
    if kind == "string_too_short":
        if not str(error.get("input", "")).strip():
            return "This field is required."
        return f"Must be at least {limits['min_length']} characters."
    if kind == "string_too_long":
        return f"Must be at most {limits['max_length']} characters."
    if kind == "enum":
        return "Choose one of the options."
    return error["msg"]


def form_errors(exc: ValidationError) -> dict[str, str]:
    errors: dict[str, str] = {}
    for error in exc.errors():
        errors.setdefault(str(error["loc"][0]), error_message(error))
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
        return render_form(request, session, values, form_errors(exc), status_code=422)

    issue = services.create_issue(session, data)
    # Post/Redirect/Get: reloading the list page cannot submit the form again.
    return RedirectResponse(f"/issues?created={issue.id}", status_code=303)


@router.post("/issues/{issue_id}/resolve")
def resolve_issue_from_form(
    request: Request,
    issue_id: int,
    session: SessionDep,
    return_query: Annotated[str, Form()] = "",
) -> Response:
    issue = services.resolve_issue(session, issue_id)
    if issue is None:
        context = {"message": f"Issue #{issue_id} does not exist."}
        return render(request, "not_found.html", context, status_code=404)

    # Back to the same filtered list. The query is rebuilt from known keys only
    # and the path is fixed, so the form cannot redirect anywhere else.
    submitted = parse_qs(return_query)
    kept = [(key, submitted[key][0]) for key in (*FILTER_FIELDS, "page") if key in submitted]
    query = urlencode([*kept, ("resolved", issue.id)])
    return RedirectResponse(f"/issues?{query}", status_code=303)


@router.get("/dashboard")
def dashboard(request: Request, session: SessionDep) -> HTMLResponse:
    stats = services.get_stats(session)
    context = {
        "active": "dashboard",
        "stats": stats,
        # Bars are scaled to the biggest bar in each chart (1 avoids dividing by zero).
        "category_max": max((row.count for row in stats.by_category), default=0) or 1,
        "clinic_max": max((row.count for row in stats.by_clinic), default=0) or 1,
    }
    return render(request, "dashboard.html", context)
