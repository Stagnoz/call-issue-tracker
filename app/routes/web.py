"""HTML pages. They call the same service functions as the JSON API."""

from datetime import datetime
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app import services
from app.db import get_session
from app.models import Category, Severity, Status
from app.schemas import IssueFilters, IssueListParams

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
        "notice": list_notice(request),
        "filter_error": filter_error,
    }
    return render(request, "issues.html", context, status_code=422 if filter_error else 200)
